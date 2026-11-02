/**
 * MSW handlers implementing the spec §5 v1.1 contract over in-memory fixtures (spec §4.2
 * `DATA_SOURCE=mock`). Shared by web (`msw/node` behind the Next.js route handlers, or
 * `msw/browser`) and mobile (`msw/native`). The behavior mirrors the API's rules closely enough
 * for UI work: lazy SLA expiry + re-offer, server-authoritative accept with 409
 * OFFER_UNAVAILABLE, lifecycle with undo, completion validation + calibration label, scoped
 * Idempotency-Key replay (D12), and logout revocation (D11). It is not a security boundary.
 */
import { delay, http, HttpResponse, type HttpHandler } from 'msw';
import type { components } from '../src/schema';
import {
  CONTRACTOR_NAMES,
  createMockDb,
  MOCK_REJECTED_PASSWORD,
  uid,
  type MockDb,
  type MockUser,
  type MockWorkOrder,
} from './fixtures';
import { createScenarios, type Scenarios } from './scenarios';

type S = components['schemas'];
type Params = Record<string, string>;
interface Ctx {
  request: Request;
  params: Params;
  user: MockUser;
  body: unknown;
}

const MIN = 60_000;
const IDEMPOTENCY_KEY = /^[A-Za-z0-9._:-]{8,128}$/;

export interface MockApiOptions {
  db?: MockDb;
  scenarios?: Scenarios;
  /** Origin the handlers answer for. Default: any origin. */
  baseUrl?: string;
}

export interface MockApi {
  handlers: HttpHandler[];
  db: MockDb;
  scenarios: Scenarios;
}

/** The mock token for a user (what `POST /v1/auth/login` returns). */
export const mockToken = (u: Pick<MockUser, 'user_id' | 'token_version'>) =>
  `mock.${u.user_id}.${u.token_version}`;

export function createMockApi(options: MockApiOptions = {}): MockApi {
  const db = options.db ?? createMockDb();
  const scenarios = options.scenarios ?? createScenarios();
  const base = (options.baseUrl ?? '*').replace(/\/+$/, '');
  const iso = (ms: number) => new Date(ms).toISOString();
  const stamp = <T extends object>(body: T) => ({ ...body, server_time: iso(db.now()) });
  const ok = (body: object, status = 200) => HttpResponse.json(stamp(body), { status });
  const noContent = () => new HttpResponse(null, { status: 204 });
  const fail = (
    status: number,
    code: S['ErrorCode'],
    message: string,
    reason?: S['OfferUnavailableReason'],
  ) =>
    HttpResponse.json(stamp({ error: { code, message, ...(reason ? { reason } : {}) } }), {
      status,
    });
  const notFound = () => fail(404, 'NOT_FOUND', 'Not found');
  const forbidden = () => fail(403, 'FORBIDDEN', "You don't have access to this");
  const invalid = (message: string) => fail(422, 'VALIDATION_ERROR', message);

  // ---- state helpers --------------------------------------------------------------------
  const asset = (wo: MockWorkOrder) => db.assets.find((a) => a.id === wo.asset_id)!;
  const candidate = (wo: MockWorkOrder, cid: string | null) =>
    wo.candidates.find((c) => c.contractor_id === cid);
  const newId = () => uid(0x9000_0000 + ++db.seq);

  function uncorrected(wo: MockWorkOrder) {
    const corrected = new Set(
      wo.events.filter((e) => e.type === 'CORRECTION').map((e) => e.corrects_event_id),
    );
    return wo.events.filter((e) => e.type === 'ADVANCE' && !corrected.has(e.event_id));
  }
  const stage = (wo: MockWorkOrder) => uncorrected(wo).at(-1)?.stage ?? null;

  function reofferNext(wo: MockWorkOrder) {
    const next = wo.candidates.find((c) => c.state === 'QUEUED');
    if (next) {
      next.state = 'OFFERED';
      wo.current_contractor_id = next.contractor_id;
      wo.sla_deadline = db.now() + wo.sla_minutes * MIN;
    } else {
      wo.state = 'NO_CONTRACTORS';
      wo.current_contractor_id = null;
      wo.sla_deadline = null;
    }
  }

  /** Lazy SLA expiry (FR-5.2): every request first expires due offers and re-offers them. */
  function expireDue() {
    for (const wo of db.workorders) {
      if (wo.state !== 'PENDING' || wo.sla_deadline === null || wo.sla_deadline > db.now())
        continue;
      const c = candidate(wo, wo.current_contractor_id);
      if (c) c.state = 'EXPIRED';
      reofferNext(wo);
    }
  }

  function summary(wo: MockWorkOrder, viewer: string | null): S['OfferSummary'] {
    const a = asset(wo);
    const c = candidate(wo, viewer) ?? candidate(wo, wo.current_contractor_id) ?? wo.candidates[0]!;
    return {
      wo_id: wo.wo_id,
      asset: { id: a.id, name: a.name, subtype: a.subtype },
      site: a.site,
      symptom: wo.symptom,
      wo_source: 'dispatch',
      dispatch_state: wo.state,
      lifecycle_stage: stage(wo),
      sla_deadline:
        wo.state === 'PENDING' && wo.sla_deadline !== null ? iso(wo.sla_deadline) : null,
      match_score: c.match_score,
      match_reason: c.match_reason,
      teaser: a.teaser,
      health_score: a.health_score,
      failure_risk: a.failure_risk,
      last_advanced_at: wo.events.at(-1)?.at ?? null,
    };
  }

  function detail(wo: MockWorkOrder, viewer: MockUser) {
    const a = asset(wo);
    const body = {
      ...summary(wo, viewer.contractor_id),
      decision: a.decision ?? {
        evidence_summary: 'No equipment history yet — symptom only',
        evidence: [],
      },
      pre_diagnostic_available: a.packet !== null,
      packet: a.packet,
      lifecycle_history: wo.events,
      predicted_failure_code: wo.predicted_failure_code,
    };
    // FR-3.5: the ranked list exists only on the owner/FM variant, never for a contractor.
    if (viewer.role === 'contractor') return body;
    return {
      ...body,
      ranked_candidates: wo.candidates.map((c, i) => ({
        contractor_id: c.contractor_id,
        name: CONTRACTOR_NAMES[c.contractor_id] ?? 'Contractor',
        rank: i + 1,
        match_score: c.match_score,
        match_reason: c.match_reason,
        state: c.state,
      })),
    };
  }

  const inTenant = (user: MockUser, woId: string | undefined) =>
    db.workorders.find((w) => w.wo_id === woId && w.tenant_id === user.tenant_id);
  const isBound = (wo: MockWorkOrder, user: MockUser) =>
    user.contractor_id !== null &&
    wo.current_contractor_id === user.contractor_id &&
    ['ACCEPTED', 'IN_PROGRESS', 'COMPLETED'].includes(wo.state);
  const canRead = (wo: MockWorkOrder, user: MockUser) =>
    user.role !== 'contractor' ||
    isBound(wo, user) ||
    (wo.state === 'PENDING' && wo.current_contractor_id === user.contractor_id);

  /** Contractor-only mutation on a WO bound to the caller (owner/FM read-only, C-3). */
  function bound(ctx: Ctx): MockWorkOrder | Response {
    if (ctx.user.role !== 'contractor') return forbidden();
    const wo = inTenant(ctx.user, ctx.params.wo);
    return wo && isBound(wo, ctx.user) ? wo : notFound();
  }

  /** `/contractor/{cid}/…` must name the caller's own contractor id (C-1: else 403). */
  function contractorOf(ctx: Ctx): string | Response {
    if (ctx.user.role !== 'contractor' || ctx.user.contractor_id === null) return forbidden();
    if (ctx.params.cid !== undefined && ctx.params.cid !== ctx.user.contractor_id)
      return forbidden();
    return ctx.user.contractor_id;
  }

  // ---- request plumbing -----------------------------------------------------------------
  function principal(request: Request): MockUser | null {
    const m = /^Bearer mock\.([0-9a-f-]{36})\.(\d+)$/.exec(
      request.headers.get('Authorization') ?? '',
    );
    const user = m && db.users.find((u) => u.user_id === m[1]);
    return user && String(user.token_version) === m[2] ? user : null;
  }

  async function readJson(request: Request): Promise<unknown> {
    const text = await request.text();
    if (!text) return undefined;
    try {
      return JSON.parse(text) as unknown;
    } catch {
      return Symbol.for('invalid-json');
    }
  }

  type Handler = (ctx: Ctx) => Response | Promise<Response>;
  interface RouteOptions {
    auth?: boolean;
    /** Replay by Idempotency-Key, scoped by user + route template + target (D12). */
    idempotent?: boolean;
    multipart?: boolean;
  }

  function route(
    method: 'get' | 'post',
    template: string,
    handler: Handler,
    opts: RouteOptions = {},
  ) {
    const path = `${base}${template.replace(/\{(\w+)\}/g, ':$1')}`;
    return http[method](path, async ({ request, params }) => {
      if (scenarios.latency() > 0) await delay(scenarios.latency());
      const s = scenarios.next(request);
      if (s.kind === 'network') return HttpResponse.error();
      if (s.kind === 'fail') return fail(s.status, 'INTERNAL', 'Something went wrong on our side');
      expireDue();
      const p = params as Params;
      const user = principal(request);
      if (opts.auth !== false && !user) return fail(401, 'UNAUTHENTICATED', 'Sign in again');
      const body = opts.multipart ? undefined : await readJson(request);
      if (body === Symbol.for('invalid-json')) return invalid('Body is not valid JSON');
      const ctx: Ctx = { request, params: p, user: user!, body };
      const key = request.headers.get('Idempotency-Key');
      if (!opts.idempotent || key === null) return handler(ctx);
      if (!IDEMPOTENCY_KEY.test(key)) return invalid('Invalid Idempotency-Key');
      const scope = `${ctx.user.user_id}|${method} ${template}|${p.cid ?? ''}/${p.wo ?? ''}|${key}`;
      // Multipart bodies aren't hashed here: a reused key on a photo upload replays (the real
      // API also rejects a different file with 422, D12).
      const hash = JSON.stringify(body ?? null);
      const seen = db.idempotency.get(scope);
      if (seen && seen.hash !== hash)
        return fail(
          422,
          'IDEMPOTENCY_KEY_REUSED',
          'This request key was already used for different data',
        );
      if (seen) return replay(seen.response);
      const res = await handler(ctx);
      if (res.status < 500) {
        const text = await res.clone().text();
        db.idempotency.set(scope, {
          hash,
          response: { status: res.status, body: text ? JSON.parse(text) : null },
        });
      }
      return res;
    });
  }
  const replay = (r: { status: number; body: unknown }) =>
    r.body === null
      ? new HttpResponse(null, { status: r.status })
      : HttpResponse.json(r.body, { status: r.status });

  const keysOk = (body: unknown, allowed: string[]): body is Record<string, unknown> =>
    typeof body === 'object' &&
    body !== null &&
    !Array.isArray(body) &&
    Object.keys(body).every((k) => allowed.includes(k));

  // ---- routes ---------------------------------------------------------------------------
  const schedule: Handler = (ctx) => {
    let cid: string;
    if (ctx.params.cid !== undefined && ctx.user.role !== 'contractor') {
      // Owner/FM read-only override within the tenant (FR-1.4).
      const exists = db.workorders.some(
        (w) =>
          w.tenant_id === ctx.user.tenant_id &&
          w.candidates.some((c) => c.contractor_id === ctx.params.cid),
      );
      if (!exists) return notFound();
      cid = ctx.params.cid;
    } else {
      const c = contractorOf(ctx);
      if (c instanceof Response) return c;
      cid = c;
    }
    const mine = db.workorders.filter((w) => w.current_contractor_id === cid);
    const t = (s: string | null | undefined) => (s ? Date.parse(s) : Number.NEGATIVE_INFINITY);
    const offers = mine.filter((w) => w.state === 'PENDING').map((w) => summary(w, cid));
    const active = mine
      .filter((w) => w.state === 'ACCEPTED' || w.state === 'IN_PROGRESS')
      .map((w) => summary(w, cid));
    offers.sort((a, b) => t(a.sla_deadline) - t(b.sla_deadline));
    active.sort((a, b) => t(b.last_advanced_at) - t(a.last_advanced_at));
    return ok({ offers, active, voice_bookings: [] });
  };

  const accept: Handler = (ctx) => {
    const cid = contractorOf(ctx);
    if (cid instanceof Response) return cid;
    const wo = inTenant(ctx.user, ctx.params.wo);
    const mine = wo && candidate(wo, cid);
    if (!wo || !mine) return notFound();
    const raced =
      wo.state === 'PENDING' && wo.current_contractor_id === cid
        ? scenarios.takeRace(wo.wo_id)
        : null;
    if (raced) {
      mine.state = raced === 'expired' ? 'EXPIRED' : 'WITHDRAWN';
      if (raced === 'withdrawn') {
        wo.state = 'UNDISPATCHED';
        wo.current_contractor_id = null;
        wo.sla_deadline = null;
      } else reofferNext(wo);
    }
    if (wo.state === 'PENDING' && wo.current_contractor_id === cid) {
      mine.state = 'ACCEPTED';
      wo.state = 'ACCEPTED';
      wo.sla_deadline = null;
      return ok(detail(wo, ctx.user));
    }
    const reason =
      mine.state === 'EXPIRED' ? 'expired' : wo.current_contractor_id ? 'reassigned' : 'withdrawn';
    return fail(409, 'OFFER_UNAVAILABLE', "This offer just expired — it's been reassigned", reason);
  };

  const decline: Handler = (ctx) => {
    const cid = contractorOf(ctx);
    if (cid instanceof Response) return cid;
    const b = ctx.body ?? {};
    if (!keysOk(b, ['reason', 'note'])) return invalid('Unexpected fields');
    const reason = (b.reason ?? null) as S['DeclineReason'] | null;
    if (reason !== null && !['too_far', 'no_capacity', 'wrong_skill', 'other'].includes(reason))
      return invalid('Unknown reason');
    const note = (b.note ?? null) as string | null;
    if (note !== null && (typeof note !== 'string' || note.length > 500))
      return invalid('Note is too long');
    const wo = inTenant(ctx.user, ctx.params.wo);
    const mine = wo && candidate(wo, cid);
    if (!wo || !mine) return notFound();
    if (wo.state !== 'PENDING' || wo.current_contractor_id !== cid)
      return fail(
        409,
        'OFFER_UNAVAILABLE',
        'This offer is no longer open',
        mine.state === 'EXPIRED' ? 'expired' : 'reassigned',
      );
    mine.state = 'DECLINED';
    wo.decline = { reason, note };
    reofferNext(wo);
    return noContent();
  };

  const transition: Handler = (ctx) => {
    const wo = bound(ctx);
    if (wo instanceof Response) return wo;
    const b = ctx.body;
    if (
      !keysOk(b, ['action', 'stage', 'corrects_event_id']) ||
      !['advance', 'undo'].includes(b.action as string)
    )
      return invalid('Invalid transition request');
    const conflict = (m: string) => fail(409, 'INVALID_TRANSITION', m);
    if (wo.state === 'COMPLETED') return conflict('This job is already completed');
    const current = stage(wo);
    const at = iso(db.now());
    if (b.action === 'advance') {
      const want = b.stage;
      const allowed =
        (current === null && want === 'EN_ROUTE') || (current === 'EN_ROUTE' && want === 'ARRIVED');
      if (!allowed) return conflict(`Can't move to ${String(want)} from ${current ?? 'accepted'}`);
      wo.events.push({
        event_id: newId(),
        type: 'ADVANCE',
        stage: want,
        corrects_event_id: null,
        actor_user_id: ctx.user.user_id,
        at,
      });
      if (wo.state === 'ACCEPTED') wo.state = 'IN_PROGRESS';
    } else {
      const latest = uncorrected(wo).at(-1);
      const target = (b.corrects_event_id as string | undefined) ?? latest?.event_id;
      if (!latest || target !== latest.event_id || latest.actor_user_id !== ctx.user.user_id)
        return conflict('Only the latest step can be undone');
      wo.events.push({
        event_id: newId(),
        type: 'CORRECTION',
        stage: null,
        corrects_event_id: latest.event_id,
        actor_user_id: ctx.user.user_id,
        at,
      });
    }
    return ok({
      lifecycle_stage: stage(wo),
      event_id: wo.events.at(-1)!.event_id,
      history: wo.events,
    });
  };

  const photos: Handler = async (ctx) => {
    const wo = bound(ctx);
    if (wo instanceof Response) return wo;
    const form = await ctx.request.formData().catch(() => null);
    const file = form?.get('file');
    if (!file || typeof file === 'string') return invalid('Attach one image as "file"');
    if (!['image/jpeg', 'image/png', 'image/heic', 'image/heif'].includes(file.type))
      return fail(415, 'UNSUPPORTED_MEDIA_TYPE', 'Use a JPEG, PNG or HEIC photo');
    if (file.size > 10 * 1024 * 1024 || wo.photos.length >= 20)
      return fail(413, 'PAYLOAD_TOO_LARGE', 'Photos must be 10 MB or smaller');
    const photo_id = newId();
    wo.photos.push(photo_id);
    return ok({ photo_id }, 201);
  };

  const complete: Handler = (ctx) => {
    const wo = bound(ctx);
    if (wo instanceof Response) return wo;
    const b = ctx.body;
    const fields = [
      'failure_code',
      'actual_fault_matched',
      'parts_used',
      'labor_hours',
      'notes',
      'technician_id',
      'photo_ids',
    ];
    if (!keysOk(b, fields)) return invalid('Unexpected fields');
    const a = asset(wo);
    const code = db.failureCodes.find((c) => c.code === b.failure_code && c.subtype === a.subtype);
    const hours = b.labor_hours as number;
    const photoIds = (b.photo_ids ?? []) as string[];
    const parts = (b.parts_used ?? []) as S['PartUsed'][];
    const problems = [
      !code && 'failure_code',
      typeof b.actual_fault_matched !== 'boolean' && 'actual_fault_matched',
      !(typeof hours === 'number' && hours > 0 && hours <= 24 && Number.isInteger(hours * 4)) &&
        'labor_hours',
      b.notes != null && (typeof b.notes !== 'string' || b.notes.length > 4000) && 'notes',
      (typeof b.technician_id !== 'string' || !b.technician_id || b.technician_id.length > 120) &&
        'technician_id',
      (!Array.isArray(photoIds) ||
        photoIds.length > 4 ||
        photoIds.some((p) => !wo.photos.includes(p))) &&
        'photo_ids',
      (!Array.isArray(parts) ||
        parts.some(
          (p) => !p || typeof p.description !== 'string' || !Number.isInteger(p.qty) || p.qty < 1,
        )) &&
        'parts_used',
    ].filter(Boolean);
    if (problems.length) return invalid(`Check: ${problems.join(', ')}`);
    if (wo.completion) return fail(409, 'ALREADY_COMPLETED', 'This job is already completed');
    const predicted = db.failureCodes.find((c) => c.code === wo.predicted_failure_code);
    const label: S['CalibrationLabel'] = !predicted
      ? 'NO_PREDICTION'
      : predicted.code === code!.code
        ? 'MATCH'
        : predicted.component_group === code!.component_group
          ? 'PARTIAL'
          : 'MISS';
    wo.completion = { report: b as unknown as S['CompletionReport'], label };
    wo.state = 'COMPLETED';
    return ok({ calibration_label: label, record_updated: true });
  };

  const login: Handler = (ctx) => {
    const b = ctx.body;
    if (
      !keysOk(b, ['email', 'password']) ||
      typeof b.email !== 'string' ||
      typeof b.password !== 'string'
    )
      return invalid('Email and password are required');
    const email = b.email.normalize('NFKC').trim().toLowerCase();
    const user = db.users.find((u) => u.email === email);
    if (!user || !b.password || b.password === MOCK_REJECTED_PASSWORD)
      return fail(401, 'INVALID_CREDENTIALS', 'Email or password is incorrect');
    const profile = {
      user_id: user.user_id,
      name: user.name,
      role: user.role,
      tenant_id: user.tenant_id,
      contractor_id: user.contractor_id,
      company: user.company,
    };
    return ok({
      access_token: mockToken(user),
      token_type: 'bearer',
      expires_at: iso(db.now() + 12 * 60 * MIN),
      user: profile,
    });
  };

  const dispatchCreate: Handler = (ctx) => {
    if (ctx.user.role === 'contractor') return forbidden();
    const b = ctx.body;
    if (
      !keysOk(b, ['asset_id', 'symptom', 'sla_minutes', 'candidates']) ||
      !Array.isArray(b.candidates) ||
      typeof b.symptom !== 'string'
    )
      return invalid('Invalid dispatch request');
    const sla = b.sla_minutes as number;
    if (!Number.isInteger(sla) || sla < 1 || sla > 1440)
      return invalid('sla_minutes must be 1–1440');
    const a = db.assets.find((x) => x.id === b.asset_id && x.tenant_id === ctx.user.tenant_id);
    if (!a) return notFound();
    const cands = b.candidates as S['DispatchCandidateIn'][];
    const tenantContractors = new Set(
      db.users.filter((u) => u.tenant_id === ctx.user.tenant_id).map((u) => u.contractor_id),
    );
    if (cands.some((c) => !tenantContractors.has(c.contractor_id)))
      return invalid('Unknown contractor');
    const wo: MockWorkOrder = {
      wo_id: newId(),
      tenant_id: ctx.user.tenant_id,
      asset_id: a.id,
      symptom: b.symptom,
      state: 'PENDING',
      current_contractor_id: null,
      sla_minutes: sla,
      sla_deadline: null,
      candidates: cands.map((c) => ({
        contractor_id: c.contractor_id,
        match_score: c.match_score,
        match_reason: c.reason,
        state: 'QUEUED',
      })),
      events: [],
      photos: [],
      decline: null,
      completion: null,
      predicted_failure_code: a.predicted_failure_code,
    };
    reofferNext(wo);
    db.workorders.push(wo);
    return ok({ wo_id: wo.wo_id }, 201);
  };

  const handlers: HttpHandler[] = [
    route('get', '/v1/healthz', () => ok({ status: 'ok' }), { auth: false }),
    route('get', '/v1/readyz', () => ok({ status: 'ready', checks: { database: 'ok' } }), {
      auth: false,
    }),
    route('post', '/v1/auth/login', login, { auth: false }),
    route('post', '/v1/auth/logout', (ctx) => {
      ctx.user.token_version += 1; // D11: revokes every outstanding token for the user
      return noContent();
    }),
    route('get', '/v1/me', ({ user }) =>
      ok({
        user_id: user.user_id,
        name: user.name,
        role: user.role,
        tenant_id: user.tenant_id,
        contractor_id: user.contractor_id,
        company: user.company,
      }),
    ),
    route('get', '/v1/me/schedule', schedule),
    route('get', '/v1/contractor/{cid}/schedule', schedule),
    route('post', '/v1/me/accept/{wo}', accept, { idempotent: true }),
    route('post', '/v1/contractor/{cid}/accept/{wo}', accept, { idempotent: true }),
    route('post', '/v1/me/decline/{wo}', decline, { idempotent: true }),
    route('post', '/v1/contractor/{cid}/decline/{wo}', decline, { idempotent: true }),
    route('get', '/v1/workorders/{wo}', (ctx) => {
      const wo = inTenant(ctx.user, ctx.params.wo);
      return wo && canRead(wo, ctx.user) ? ok(detail(wo, ctx.user)) : notFound();
    }),
    route('post', '/v1/workorders/{wo}/transition', transition, { idempotent: true }),
    route('post', '/v1/workorders/{wo}/photos', photos, { idempotent: true, multipart: true }),
    route('post', '/v1/workorders/{wo}/complete', complete, { idempotent: true }),
    route('get', '/v1/failure-codes', ({ request }) => {
      const subtype = new URL(request.url).searchParams.get('subtype');
      return ok({
        failure_codes: db.failureCodes.filter((c) => !subtype || c.subtype === subtype),
      });
    }),
    route('post', '/v1/dispatch/workorders', dispatchCreate, { idempotent: true }),
  ];

  return { handlers, db, scenarios };
}
