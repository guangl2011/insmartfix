/* eslint-disable @typescript-eslint/no-explicit-any -- response bodies are untyped JSON whose shape Ajv checks against openapi.json in conforms(). */
// M3-T2: the MSW contract mocks implement spec §5 v1.1, and every response they produce
// validates against openapi.json (status declared + JSON body matches the schema).
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import Ajv2020 from 'ajv/dist/2020';
import addFormats from 'ajv-formats';
import { setupServer } from 'msw/node';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import {
  applyScenarioString,
  ASSET,
  CONTRACTOR,
  createMockApi,
  createMockDb,
  createScenarios,
  MOCK_REJECTED_PASSWORD,
  uid,
  WO,
  type MockApi,
} from '../mocks/index';

const BASE = 'http://mock.api';
const doc = JSON.parse(
  readFileSync(fileURLToPath(new URL('../openapi.json', import.meta.url)), 'utf8'),
) as {
  paths: Record<
    string,
    Record<string, { responses: Record<string, { content?: Record<string, { schema: unknown }> }> }>
  >;
};
const ajv = new Ajv2020({ strict: false, allErrors: true });
addFormats(ajv);
ajv.addSchema(doc as object, 'openapi.json');
const pointer = (...parts: string[]) =>
  parts.map((p) => encodeURIComponent(p.replace(/~/g, '~0').replace(/\//g, '~1'))).join('/');

/** Asserts `res` is a declared response of the operation and its JSON body matches the schema. */
async function conforms(method: string, template: string, res: Response): Promise<any> {
  const op = doc.paths[template]?.[method.toLowerCase()];
  expect(op, `${method} ${template} is in openapi.json`).toBeDefined();
  const declared = op!.responses[String(res.status)];
  // Injected 5xx (scenarios) are outside the declared responses by nature; they still carry
  // the standard error envelope.
  const injected = !declared && res.status >= 500;
  expect(declared ?? injected, `${method} ${template} declares ${res.status}`).toBeTruthy();
  const text = await res.text();
  if (!injected && !declared!.content?.['application/json']) {
    expect(text).toBe('');
    return undefined;
  }
  const body = JSON.parse(text);
  const ref = injected
    ? `openapi.json#/${pointer('components', 'schemas', 'ErrorEnvelope')}`
    : `openapi.json#/${pointer('paths', template, method.toLowerCase(), 'responses', String(res.status), 'content', 'application/json', 'schema')}`;
  const validate = ajv.getSchema(ref) ?? ajv.compile({ $ref: ref });
  const valid = validate(body);
  expect(valid, `${method} ${template} ${res.status}: ${ajv.errorsText(validate.errors)}`).toBe(
    true,
  );
  expect(typeof body.server_time).toBe('string');
  return body;
}

let now = Date.parse('2026-11-02T15:00:00Z');
let mock: MockApi;
const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterAll(() => server.close());
beforeEach(() => {
  now = Date.parse('2026-11-02T15:00:00Z');
  mock = createMockApi({ db: createMockDb({ now: () => now }), baseUrl: BASE });
  server.resetHandlers(...mock.handlers);
});
afterEach(() => server.resetHandlers());

interface Call {
  method?: string;
  token?: string | null;
  body?: unknown;
  key?: string;
  form?: FormData;
}
async function call(template: string, params: Record<string, string> = {}, c: Call = {}) {
  const method = c.method ?? (c.body !== undefined || c.form ? 'POST' : 'GET');
  const path = template.replace(/\{(\w+)\}/g, (_, k: string) => params[k]!);
  const headers: Record<string, string> = {};
  if (c.token) headers.Authorization = `Bearer ${c.token}`;
  if (c.key) headers['Idempotency-Key'] = c.key;
  if (c.body !== undefined) headers['content-type'] = 'application/json';
  const res = await fetch(`${BASE}${path}${params.query ?? ''}`, {
    method,
    headers,
    body: c.form ?? (c.body !== undefined ? JSON.stringify(c.body) : undefined),
  });
  return { status: res.status, body: await conforms(method, template, res) };
}
async function login(email: string): Promise<string> {
  const r = await call('/v1/auth/login', {}, { body: { email, password: 'any-mock-password' } });
  expect(r.status).toBe(200);
  return r.body.access_token as string;
}

describe('coverage of the contract', () => {
  it('has exactly one handler per openapi.json operation', () => {
    const ops = Object.entries(doc.paths).flatMap(([p, o]) =>
      Object.keys(o).map((m) => `${m.toUpperCase()} ${p}`),
    );
    const handled = mock.handlers.map((h) => {
      const info = h.info as { method: string; path: string };
      return `${info.method} ${info.path.slice(BASE.length).replace(/:(\w+)/g, '{$1}')}`;
    });
    expect(handled.sort()).toEqual(ops.sort());
  });
});

describe('auth (FR-1.1, D11 logout)', () => {
  it('logs in known users, rejects bad credentials and unauthenticated calls', async () => {
    const token = await login('  Marco@Test.Insmart.AI ');
    expect((await call('/v1/me', {}, { token })).body).toMatchObject({
      name: 'Marco Rossi',
      role: 'contractor',
      contractor_id: CONTRACTOR.marco,
      company: 'Rossi HVAC',
    });
    for (const body of [
      { email: 'marco@test.insmart.ai', password: MOCK_REJECTED_PASSWORD },
      { email: 'nobody@test.insmart.ai', password: 'x' },
    ]) {
      const r = await call('/v1/auth/login', {}, { body });
      expect(r).toMatchObject({
        status: 401,
        body: { error: { code: 'INVALID_CREDENTIALS', message: 'Email or password is incorrect' } },
      });
    }
    expect(
      (await call('/v1/auth/login', {}, { body: { email: 'a', password: 'b', extra: 1 } })).status,
    ).toBe(422);
    expect((await call('/v1/me')).body.error.code).toBe('UNAUTHENTICATED');
    expect((await call('/v1/me', {}, { token: 'mock.garbage' })).status).toBe(401);
  });

  it('POST /auth/logout returns 204 and revokes every token of the user', async () => {
    const t1 = await login('marco@test.insmart.ai');
    expect((await call('/v1/auth/logout', {}, { method: 'POST', token: t1 })).status).toBe(204);
    expect((await call('/v1/me/schedule', {}, { token: t1 })).status).toBe(401);
    const t2 = await login('marco@test.insmart.ai');
    expect(t2).not.toBe(t1);
    expect((await call('/v1/me', {}, { token: t2 })).status).toBe(200);
    expect((await call('/v1/auth/logout', {}, { method: 'POST' })).status).toBe(401);
  });

  it('serves health and readiness without auth', async () => {
    expect((await call('/v1/healthz')).body.status).toBe('ok');
    expect((await call('/v1/readyz')).body.status).toBe('ready');
  });
});

describe('schedule and SLA fixtures (TEST_PLAN §5)', () => {
  it('lists Marco’s offers by soonest deadline and active jobs by most recent advance', async () => {
    const token = await login('marco@test.insmart.ai');
    const { body } = await call('/v1/me/schedule', {}, { token });
    // The past-deadline offer was expired lazily and re-offered to Ana (FR-5.2).
    expect(body.offers.map((o: any) => o.wo_id)).toEqual([WO.rtu45s, WO.ahu4m, WO.rtu12m]);
    expect(body.offers.map((o: any) => Date.parse(o.sla_deadline) - now)).toEqual([
      45_000,
      4 * 60_000,
      12 * 60_000,
    ]);
    expect(body.active.map((o: any) => [o.wo_id, o.lifecycle_stage])).toEqual([
      [WO.arrived, 'ARRIVED'],
      [WO.accepted, null],
    ]);
    expect(body.voice_bookings).toEqual([]);
    expect(body.offers[2]).toMatchObject({
      teaser: { likely_cause: 'Compressor contactor', confidence: 0.82 },
      health_score: 44,
      failure_risk: 'HIGH',
    });
    const ana = await login('ana@test.insmart.ai');
    expect(
      (
        await call('/v1/contractor/{cid}/schedule', { cid: CONTRACTOR.ana }, { token: ana })
      ).body.offers.map((o: any) => o.wo_id),
    ).toEqual([WO.anaOffer, WO.ahuPast]);
  });

  it('expires an offer once its deadline passes and re-offers it (sweeper-free, lazy)', async () => {
    const token = await login('marco@test.insmart.ai');
    now += 46_000;
    const { body } = await call('/v1/me/schedule', {}, { token });
    expect(body.offers.map((o: any) => o.wo_id)).not.toContain(WO.rtu45s);
    expect(
      (await call('/v1/me/accept/{wo}', { wo: WO.rtu45s }, { method: 'POST', token })).body.error,
    ).toEqual({
      code: 'OFFER_UNAVAILABLE',
      message: "This offer just expired — it's been reassigned",
      reason: 'expired',
    });
  });
});

describe('identity rules (FR-1.4, C-1, C-3, FR-3.5)', () => {
  it('scopes contractors to themselves and gives owners a read-only override', async () => {
    const marco = await login('marco@test.insmart.ai');
    const owner = await login('owner@test.insmart.ai');
    const zed = await login('zed@other.insmart.ai');
    expect(
      (await call('/v1/contractor/{cid}/schedule', { cid: CONTRACTOR.ana }, { token: marco }))
        .status,
    ).toBe(403);
    expect(
      (
        await call(
          '/v1/contractor/{cid}/accept/{wo}',
          { cid: CONTRACTOR.ana, wo: WO.anaOffer },
          { method: 'POST', token: marco },
        )
      ).status,
    ).toBe(403);
    expect((await call('/v1/workorders/{wo}', { wo: WO.rtu12m }, { token: zed })).status).toBe(404);
    expect((await call('/v1/workorders/{wo}', { wo: WO.anaOffer }, { token: marco })).status).toBe(
      404,
    );
    const ownerSchedule = await call(
      '/v1/contractor/{cid}/schedule',
      { cid: CONTRACTOR.marco },
      { token: owner },
    );
    expect(ownerSchedule.body.offers).toHaveLength(3);
    expect(
      (await call('/v1/contractor/{cid}/schedule', { cid: CONTRACTOR.zed }, { token: owner }))
        .status,
    ).toBe(404);
    expect((await call('/v1/me/schedule', {}, { token: owner })).status).toBe(403);
    const ownerDetail = await call('/v1/workorders/{wo}', { wo: WO.rtu12m }, { token: owner });
    expect(ownerDetail.body.ranked_candidates.map((c: any) => [c.name, c.rank])).toEqual([
      ['Marco Rossi', 1],
      ['Ana Lee', 2],
    ]);
    expect(
      (await call('/v1/me/accept/{wo}', { wo: WO.rtu12m }, { method: 'POST', token: owner }))
        .status,
    ).toBe(403);
    expect(
      (
        await call(
          '/v1/workorders/{wo}/transition',
          { wo: WO.arrived },
          { token: owner, body: { action: 'undo' } },
        )
      ).status,
    ).toBe(403);
    const contractorDetail = await call('/v1/workorders/{wo}', { wo: WO.rtu12m }, { token: marco });
    expect(contractorDetail.body).not.toHaveProperty('ranked_candidates');
  });
});

describe('work-order detail (FR-3.1–3.6)', () => {
  it('returns the full packet for RTU-04 and the honest no-packet shape for AHU-NEW-01', async () => {
    const token = await login('marco@test.insmart.ai');
    const rtu = (await call('/v1/workorders/{wo}', { wo: WO.rtu12m }, { token })).body;
    expect(rtu).toMatchObject({
      pre_diagnostic_available: true,
      predicted_failure_code: 'COMP-CONTACTOR',
      decision: { health_score: 44, failure_risk: 'HIGH' },
    });
    expect(Object.keys(rtu.packet).sort()).toEqual([
      'active_insights',
      'asset_identity',
      'predicted_parts',
      'recent_events',
      'recent_maintenance',
    ]);
    const ahu = (await call('/v1/workorders/{wo}', { wo: WO.ahu4m }, { token })).body;
    expect(ahu).toMatchObject({
      pre_diagnostic_available: false,
      packet: null,
      predicted_failure_code: null,
    });
    expect(ahu.decision.root_cause).toBeUndefined();
  });
});

describe('the core loop: accept → en route → arrived (undo) → photo → complete', () => {
  it('runs end to end with idempotent replays and calibration', async () => {
    const token = await login('marco@test.insmart.ai');
    const accepted = await call(
      '/v1/me/accept/{wo}',
      { wo: WO.rtu12m },
      { method: 'POST', token, key: 'accept-key-1' },
    );
    expect(accepted.body).toMatchObject({
      dispatch_state: 'ACCEPTED',
      pre_diagnostic_available: true,
    });
    expect(accepted.body.packet.predicted_parts).toHaveLength(1);
    // Same key → same result even though the offer is no longer pending.
    expect(
      (
        await call(
          '/v1/me/accept/{wo}',
          { wo: WO.rtu12m },
          { method: 'POST', token, key: 'accept-key-1' },
        )
      ).body,
    ).toEqual(accepted.body);
    const wo = { wo: WO.rtu12m };
    const t = (body: unknown, key?: string) =>
      call('/v1/workorders/{wo}/transition', wo, { token, body, ...(key ? { key } : {}) });
    expect((await t({ action: 'advance', stage: 'ARRIVED' })).status).toBe(409);
    const enRoute = await t({ action: 'advance', stage: 'EN_ROUTE' }, 'adv-en-route');
    expect(enRoute.body.lifecycle_stage).toBe('EN_ROUTE');
    expect((await t({ action: 'advance', stage: 'EN_ROUTE' }, 'adv-en-route')).body.event_id).toBe(
      enRoute.body.event_id,
    );
    expect((await t({ action: 'advance', stage: 'ARRIVED' }, 'adv-en-route')).body.error.code).toBe(
      'IDEMPOTENCY_KEY_REUSED',
    );
    const arrived = await t({ action: 'advance', stage: 'ARRIVED' });
    const undo = await t({ action: 'undo' });
    expect(undo.body).toMatchObject({ lifecycle_stage: 'EN_ROUTE' });
    expect(undo.body.history.at(-1)).toMatchObject({
      type: 'CORRECTION',
      corrects_event_id: arrived.body.event_id,
    });
    expect((await t({ action: 'undo', corrects_event_id: arrived.body.event_id })).status).toBe(
      409,
    );
    expect((await t({ action: 'advance', stage: 'ARRIVED' })).body.lifecycle_stage).toBe('ARRIVED');
    expect((await t({ action: 'jump' })).status).toBe(422);

    const form = (type: string, size = 10) => {
      const f = new FormData();
      f.set('file', new File([new Uint8Array(size)], 'p.jpg', { type }));
      return f;
    };
    const photo = await call('/v1/workorders/{wo}/photos', wo, { token, form: form('image/jpeg') });
    expect(photo.status).toBe(201);
    expect(
      (await call('/v1/workorders/{wo}/photos', wo, { token, form: form('application/pdf') }))
        .status,
    ).toBe(415);
    expect(
      (
        await call('/v1/workorders/{wo}/photos', wo, {
          token,
          form: form('image/png', 10 * 1024 * 1024 + 1),
        })
      ).status,
    ).toBe(413);
    expect(
      (await call('/v1/workorders/{wo}/photos', wo, { token, form: new FormData() })).status,
    ).toBe(422);

    const report = {
      failure_code: 'COMP-CONTACTOR',
      actual_fault_matched: true,
      parts_used: [{ part_code: 'CNT-3P-40A', description: 'Contactor', qty: 1 }],
      labor_hours: 1.5,
      notes: 'Replaced contactor',
      technician_id: 'Marco Rossi',
      photo_ids: [photo.body.photo_id],
    };
    const done = (body: unknown, key: string) =>
      call('/v1/workorders/{wo}/complete', wo, { token, body, key });
    expect(
      (await done({ ...report, labor_hours: 1.3 }, 'complete-bad-1')).body.error,
    ).toMatchObject({ code: 'VALIDATION_ERROR' });
    expect((await done({ ...report, photo_ids: [uid(0xdead)] }, 'complete-bad-2')).status).toBe(
      422,
    );
    expect((await done({ ...report, label: 'MATCH' }, 'complete-bad-3')).status).toBe(422);
    const first = await done(report, 'complete-key-1');
    expect(first.body).toMatchObject({ calibration_label: 'MATCH', record_updated: true });
    expect((await done(report, 'complete-key-1')).body).toEqual(first.body);
    expect((await done(report, 'complete-key-2')).body.error.code).toBe('ALREADY_COMPLETED');
    expect((await t({ action: 'undo' })).status).toBe(409);
    const schedule = (await call('/v1/me/schedule', {}, { token })).body;
    expect([...schedule.offers, ...schedule.active].map((o: any) => o.wo_id)).not.toContain(
      WO.rtu12m,
    );
  });

  it('labels PARTIAL, MISS and NO_PREDICTION (FR-7.5)', async () => {
    const token = await login('marco@test.insmart.ai');
    const complete = (wo: string, failure_code: string) =>
      call(
        '/v1/workorders/{wo}/complete',
        { wo },
        {
          token,
          body: {
            failure_code,
            actual_fault_matched: false,
            labor_hours: 2,
            technician_id: 'Marco Rossi',
          },
        },
      );
    expect((await complete(WO.arrived, 'COMP-CAPACITOR')).body.calibration_label).toBe('PARTIAL');
    expect((await complete(WO.accepted, 'BLWR-BELT')).body.calibration_label).toBe('NO_PREDICTION');
    await call('/v1/me/accept/{wo}', { wo: WO.rtu45s }, { method: 'POST', token });
    expect((await complete(WO.rtu45s, 'FAN-MOTOR')).body.calibration_label).toBe('MISS');
    expect((await complete(WO.rtu12m, 'FAN-MOTOR')).status).toBe(404); // not accepted yet
  });
});

describe('decline (FR-4.2, FR-4.3)', () => {
  it('records the reason, re-offers to the next candidate, and validates input', async () => {
    const marco = await login('marco@test.insmart.ai');
    expect(
      (
        await call(
          '/v1/me/decline/{wo}',
          { wo: WO.ahu4m },
          { token: marco, body: { reason: 'far' } },
        )
      ).status,
    ).toBe(422);
    expect(
      (
        await call(
          '/v1/me/decline/{wo}',
          { wo: WO.ahu4m },
          { token: marco, body: { note: 'x'.repeat(501) } },
        )
      ).status,
    ).toBe(422);
    expect(
      (
        await call(
          '/v1/me/decline/{wo}',
          { wo: WO.ahu4m },
          { token: marco, body: { reason: 'too_far', why: 1 } },
        )
      ).status,
    ).toBe(422);
    expect(
      (
        await call(
          '/v1/me/decline/{wo}',
          { wo: WO.ahu4m },
          { token: marco, body: { reason: 'too_far', note: 'Across town' } },
        )
      ).status,
    ).toBe(204);
    expect(mock.db.workorders.find((w) => w.wo_id === WO.ahu4m)!.decline).toEqual({
      reason: 'too_far',
      note: 'Across town',
    });
    expect(
      (await call('/v1/me/decline/{wo}', { wo: WO.ahu4m }, { token: marco, body: {} })).status,
    ).toBe(409);
    // Skip: one-tap decline with no body.
    expect(
      (
        await call(
          '/v1/contractor/{cid}/decline/{wo}',
          { cid: CONTRACTOR.marco, wo: WO.rtu45s },
          { method: 'POST', token: marco },
        )
      ).status,
    ).toBe(204);
    const ana = await login('ana@test.insmart.ai');
    const anaOffers = (await call('/v1/me/schedule', {}, { token: ana })).body.offers.map(
      (o: any) => o.wo_id,
    );
    expect(anaOffers).toEqual(expect.arrayContaining([WO.ahu4m, WO.rtu45s]));
    // Ana is the last candidate: declining leaves NO_CONTRACTORS (visible to the owner).
    await call('/v1/me/decline/{wo}', { wo: WO.ahu4m }, { method: 'POST', token: ana });
    const owner = await login('owner@test.insmart.ai');
    expect(
      (await call('/v1/workorders/{wo}', { wo: WO.ahu4m }, { token: owner })).body.dispatch_state,
    ).toBe('NO_CONTRACTORS');
    expect(
      (await call('/v1/me/decline/{wo}', { wo: WO.zedOffer }, { method: 'POST', token: marco }))
        .status,
    ).toBe(404);
  });
});

describe('scenarios: 409 race, 5xx, network errors, latency', () => {
  it.each(['reassigned', 'expired', 'withdrawn'] as const)(
    'race (%s): the next accept gets 409 OFFER_UNAVAILABLE and the offer leaves the schedule',
    async (reason) => {
      const token = await login('marco@test.insmart.ai');
      mock.scenarios.raceOffer(WO.ahu4m, reason);
      const r = await call('/v1/me/accept/{wo}', { wo: WO.ahu4m }, { method: 'POST', token });
      expect(r).toMatchObject({
        status: 409,
        body: { error: { code: 'OFFER_UNAVAILABLE', reason } },
      });
      expect(
        (await call('/v1/me/schedule', {}, { token })).body.offers.map((o: any) => o.wo_id),
      ).not.toContain(WO.ahu4m);
      // The race is one-shot.
      expect(mock.scenarios.takeRace(WO.ahu4m)).toBeNull();
    },
  );

  it('fails the next matching requests with 5xx, then recovers', async () => {
    const token = await login('marco@test.insmart.ai');
    mock.scenarios.failNext(503, 2, { path: '/schedule', method: 'GET' });
    expect((await call('/v1/me/schedule', {}, { token })).body.error.code).toBe('INTERNAL');
    expect((await call('/v1/me', {}, { token })).status).toBe(200);
    expect((await call('/v1/me/schedule', {}, { token })).status).toBe(503);
    expect((await call('/v1/me/schedule', {}, { token })).status).toBe(200);
    mock.scenarios.failNext(500, 1, { path: /\/complete$/ });
    expect(
      (await call('/v1/workorders/{wo}/complete', { wo: WO.arrived }, { token, body: {} })).status,
    ).toBe(500);
  });

  it('simulates network failures and latency', async () => {
    mock.scenarios.networkErrorNext(1, { path: '/healthz' });
    await expect(fetch(`${BASE}/v1/healthz`)).rejects.toThrow();
    expect((await fetch(`${BASE}/v1/healthz`)).status).toBe(200);
    mock.scenarios.setLatency(60);
    const started = performance.now();
    await fetch(`${BASE}/v1/healthz`);
    expect(performance.now() - started).toBeGreaterThanOrEqual(50);
    mock.scenarios.reset();
    expect(mock.scenarios.latency()).toBe(0);
  });

  it('parses MOCK_SCENARIOS for pnpm dev:mock', () => {
    const s = createScenarios();
    applyScenarioString(
      s,
      'latency=800, race, race=abc:expired, fail=503:2:/complete, network=3:/schedule',
      WO.ahu4m,
    );
    expect(s.latency()).toBe(800);
    expect(s.takeRace(WO.ahu4m)).toBe('reassigned');
    expect(s.takeRace('abc')).toBe('expired');
    const req = (p: string) => new Request(`${BASE}${p}`);
    expect(s.next(req('/v1/me/schedule'))).toEqual({ kind: 'network' });
    expect(s.next(req('/v1/workorders/x/complete'))).toEqual({ kind: 'fail', status: 503 });
    applyScenarioString(s, '', WO.ahu4m);
    for (const bad of ['latency=fast', 'fail=418', 'chaos'])
      expect(() => applyScenarioString(s, bad, WO.ahu4m)).toThrow(/MOCK_SCENARIOS/);
  });
});

describe('catalog and dispatch (FR-7.1, FR-10.1)', () => {
  it('filters failure codes by subtype', async () => {
    const token = await login('marco@test.insmart.ai');
    const rtu = (await call('/v1/failure-codes', { query: '?subtype=RTU' }, { token })).body
      .failure_codes;
    expect(rtu.every((c: any) => c.subtype === 'RTU')).toBe(true);
    expect(rtu.map((c: any) => c.code)).toContain('COMP-CONTACTOR');
    expect(
      (await call('/v1/failure-codes', {}, { token })).body.failure_codes.length,
    ).toBeGreaterThan(rtu.length);
  });

  it('lets an owner create a dispatch that is offered to rank 1; contractors get 403', async () => {
    const owner = await login('owner@test.insmart.ai');
    const req = {
      asset_id: ASSET.rtu04,
      symptom: 'Smoke smell',
      sla_minutes: 15,
      candidates: [{ contractor_id: CONTRACTOR.ana, match_score: 0.9, reason: 'Closest' }],
    };
    const created = await call('/v1/dispatch/workorders', {}, { token: owner, body: req });
    expect(created.status).toBe(201);
    const ana = await login('ana@test.insmart.ai');
    const offer = (await call('/v1/me/schedule', {}, { token: ana })).body.offers.find(
      (o: any) => o.wo_id === created.body.wo_id,
    );
    expect(Date.parse(offer.sla_deadline) - now).toBe(15 * 60_000);
    expect((await call('/v1/dispatch/workorders', {}, { token: ana, body: req })).status).toBe(403);
    expect(
      (
        await call(
          '/v1/dispatch/workorders',
          {},
          { token: owner, body: { ...req, asset_id: ASSET.zedRtu } },
        )
      ).status,
    ).toBe(404);
    expect(
      (
        await call(
          '/v1/dispatch/workorders',
          {},
          {
            token: owner,
            body: { ...req, candidates: [{ ...req.candidates[0], contractor_id: CONTRACTOR.zed }] },
          },
        )
      ).status,
    ).toBe(422);
    expect(
      (
        await call(
          '/v1/dispatch/workorders',
          {},
          { token: owner, body: { ...req, sla_minutes: 0 } },
        )
      ).status,
    ).toBe(422);
    expect(
      (
        await call(
          '/v1/dispatch/workorders',
          {},
          { token: owner, body: { ...req, candidates: [] } },
        )
      ).status,
    ).toBe(201);
  });
});
