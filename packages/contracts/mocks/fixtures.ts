/**
 * In-memory fixtures mirroring TEST_PLAN §5 (Midtown Properties, Marco, Ana, Zed, RTU-04,
 * AHU-NEW-01, offers at 12 m / 4 m / 45 s / past deadline, one ACCEPTED and one ARRIVED job).
 * `createMockDb()` returns fresh mutable state; deadlines are relative to the db clock.
 * Mock-only data: no real accounts, and no passwords (any password except
 * MOCK_REJECTED_PASSWORD signs a known email in).
 */
import type { components } from '../src/schema';

type S = components['schemas'];

/** Deterministic UUIDv4-shaped ids. */
export const uid = (n: number) => `00000000-0000-4000-8000-${n.toString(16).padStart(12, '0')}`;

export const MOCK_REJECTED_PASSWORD = 'wrong-password';

export const TENANT = { midtown: uid(0x100), other: uid(0x101) };

export interface MockUser {
  user_id: string;
  email: string;
  name: string;
  role: S['Role'];
  tenant_id: string;
  contractor_id: string | null;
  company: string | null;
  token_version: number;
}

export const CONTRACTOR = { marco: uid(0x200), ana: uid(0x201), zed: uid(0x202) };

const users = (): MockUser[] => [
  {
    user_id: uid(0x300),
    email: 'marco@test.insmart.ai',
    name: 'Marco Rossi',
    role: 'contractor',
    tenant_id: TENANT.midtown,
    contractor_id: CONTRACTOR.marco,
    company: 'Rossi HVAC',
    token_version: 0,
  },
  {
    user_id: uid(0x301),
    email: 'ana@test.insmart.ai',
    name: 'Ana Lee',
    role: 'contractor',
    tenant_id: TENANT.midtown,
    contractor_id: CONTRACTOR.ana,
    company: 'Lee Mechanical',
    token_version: 0,
  },
  {
    user_id: uid(0x302),
    email: 'owner@test.insmart.ai',
    name: 'Dana Owner',
    role: 'owner',
    tenant_id: TENANT.midtown,
    contractor_id: null,
    company: 'Midtown Properties',
    token_version: 0,
  },
  {
    user_id: uid(0x303),
    email: 'zed@other.insmart.ai',
    name: 'Zed',
    role: 'contractor',
    tenant_id: TENANT.other,
    contractor_id: CONTRACTOR.zed,
    company: 'Zed Air',
    token_version: 0,
  },
];

export const CONTRACTOR_NAMES: Record<string, string> = {
  [CONTRACTOR.marco]: 'Marco Rossi',
  [CONTRACTOR.ana]: 'Ana Lee',
  [CONTRACTOR.zed]: 'Zed',
};

export interface MockAsset {
  id: string;
  tenant_id: string;
  name: string;
  subtype: string;
  site: S['SiteRef'];
  identity: S['AssetIdentity'];
  /** Present only when the engine has history (RTU-04). */
  packet: S['Packet'] | null;
  decision: S['Decision'] | null;
  teaser: S['Teaser'];
  health_score: number | null;
  failure_risk: S['FailureRisk'] | null;
  predicted_failure_code: string | null;
}

export const ASSET = { rtu04: uid(0x400), ahuNew01: uid(0x401), zedRtu: uid(0x402) };

const MIN = 60_000;
const DAY = 24 * 60 * MIN;

function assets(now: number): MockAsset[] {
  const ago = (ms: number) => new Date(now - ms).toISOString();
  const tower = { name: 'Midtown Tower', location: 'Roof, north bay' };
  return [
    {
      id: ASSET.rtu04,
      tenant_id: TENANT.midtown,
      name: 'RTU-04',
      subtype: 'RTU',
      site: tower,
      identity: {
        name: 'RTU-04',
        subtype: 'RTU',
        make: 'Carrier',
        model: '48TC',
        install_year: 2014,
        location: 'Midtown Tower Roof',
        duty: 'Rooftop unit, floors 30–34',
      },
      packet: {
        asset_identity: {
          name: 'RTU-04',
          subtype: 'RTU',
          make: 'Carrier',
          model: '48TC',
          install_year: 2014,
          location: 'Midtown Tower Roof',
          duty: 'Rooftop unit, floors 30–34',
        },
        recent_events: [
          { at: ago(2 * DAY), kind: 'alarm', summary: 'Compressor short-cycling (6 starts/h)' },
          { at: ago(5 * DAY), kind: 'trend', summary: 'Contactor coil resistance drifting up 18%' },
          { at: ago(9 * DAY), kind: 'alarm', summary: 'High discharge temperature, cleared' },
        ],
        recent_maintenance: [
          {
            at: ago(120 * DAY),
            summary: 'Quarterly PM, filters replaced',
            performed_by: 'Rossi HVAC',
          },
        ],
        active_insights: [
          {
            summary: 'Contactor wear pattern matches 82% of prior contactor failures',
            confidence: 0.82,
          },
          { summary: 'Phase imbalance 3.1% on L2', confidence: 0.64 },
        ],
        predicted_parts: [
          {
            description: 'Compressor contactor, 3-pole 40 A',
            part_code: 'CNT-3P-40A',
            qty: 1,
            likelihood: 0.82,
          },
        ],
      },
      decision: {
        health_score: 44,
        failure_risk: 'HIGH',
        root_cause: 'Compressor contactor failing — coil resistance drift + short-cycling pattern',
        recommended_action: 'Replace contactor; verify phase balance before restart',
        evidence_summary: 'Based on 3 recent events + 2 active insights',
        evidence: [
          { kind: 'event', summary: 'Compressor short-cycling (6 starts/h)', at: ago(2 * DAY) },
          { kind: 'event', summary: 'Contactor coil resistance drifting up 18%', at: ago(5 * DAY) },
          { kind: 'event', summary: 'High discharge temperature, cleared', at: ago(9 * DAY) },
          { kind: 'insight', summary: 'Contactor wear pattern matches prior failures' },
          { kind: 'insight', summary: 'Phase imbalance 3.1% on L2' },
        ],
      },
      teaser: { likely_cause: 'Compressor contactor', confidence: 0.82 },
      health_score: 44,
      failure_risk: 'HIGH',
      predicted_failure_code: 'COMP-CONTACTOR',
    },
    {
      id: ASSET.ahuNew01,
      tenant_id: TENANT.midtown,
      name: 'AHU-NEW-01',
      subtype: 'AHU',
      site: { name: 'Midtown Tower', location: 'Mechanical room, level 2' },
      identity: {
        name: 'AHU-NEW-01',
        subtype: 'AHU',
        make: 'Trane',
        model: 'Performance',
        install_year: 2026,
        location: 'Mechanical room, level 2',
        duty: 'Air handler, lobby',
      },
      packet: null,
      decision: null,
      teaser: {},
      health_score: null,
      failure_risk: null,
      predicted_failure_code: null,
    },
    {
      id: ASSET.zedRtu,
      tenant_id: TENANT.other,
      name: 'OT-RTU-1',
      subtype: 'RTU',
      site: { name: 'Other Plaza', location: 'Roof' },
      identity: { name: 'OT-RTU-1', subtype: 'RTU' },
      packet: null,
      decision: null,
      teaser: {},
      health_score: null,
      failure_risk: null,
      predicted_failure_code: null,
    },
  ];
}

export const FAILURE_CODES: S['FailureCode'][] = [
  {
    code: 'COMP-CONTACTOR',
    subtype: 'RTU',
    component_group: 'compressor',
    label: 'Compressor contactor failed',
  },
  {
    code: 'COMP-CAPACITOR',
    subtype: 'RTU',
    component_group: 'compressor',
    label: 'Compressor run capacitor failed',
  },
  {
    code: 'COMP-MOTOR',
    subtype: 'RTU',
    component_group: 'compressor',
    label: 'Compressor motor failed',
  },
  {
    code: 'FAN-MOTOR',
    subtype: 'RTU',
    component_group: 'condenser-fan',
    label: 'Condenser fan motor failed',
  },
  {
    code: 'REFRIG-LEAK',
    subtype: 'RTU',
    component_group: 'refrigerant',
    label: 'Refrigerant leak',
  },
  { code: 'BLWR-MOTOR', subtype: 'AHU', component_group: 'blower', label: 'Blower motor failed' },
  {
    code: 'BLWR-BELT',
    subtype: 'AHU',
    component_group: 'blower',
    label: 'Blower belt worn or broken',
  },
  { code: 'FILTER-CLOG', subtype: 'AHU', component_group: 'airflow', label: 'Filters clogged' },
  {
    code: 'CTRL-SENSOR',
    subtype: 'AHU',
    component_group: 'controls',
    label: 'Supply air sensor failed',
  },
];

export interface MockCandidate {
  contractor_id: string;
  match_score: number;
  match_reason: string;
  state: S['CandidateState'];
}

export interface MockWorkOrder {
  wo_id: string;
  tenant_id: string;
  asset_id: string;
  symptom: string;
  state: S['DispatchState'];
  current_contractor_id: string | null;
  sla_minutes: number;
  sla_deadline: number | null;
  /** Ranked; index 0 is rank 1. */
  candidates: MockCandidate[];
  events: S['LifecycleEvent'][];
  photos: string[];
  decline: { reason: S['DeclineReason'] | null; note: string | null } | null;
  completion: { report: S['CompletionReport']; label: S['CalibrationLabel'] } | null;
  /** Prediction snapshot taken at dispatch (D10 L-4). */
  predicted_failure_code: string | null;
}

export const WO = {
  rtu12m: uid(0x500),
  ahu4m: uid(0x501),
  rtu45s: uid(0x502),
  ahuPast: uid(0x503),
  accepted: uid(0x504),
  arrived: uid(0x505),
  anaOffer: uid(0x506),
  zedOffer: uid(0x507),
};

export interface MockDb {
  now: () => number;
  users: MockUser[];
  assets: MockAsset[];
  workorders: MockWorkOrder[];
  failureCodes: S['FailureCode'][];
  idempotency: Map<string, { hash: string; response: { status: number; body: unknown } }>;
  seq: number;
}

export function createMockDb(options: { now?: () => number } = {}): MockDb {
  const now = options.now ?? Date.now;
  const t = now();
  const m = (n: number) => t + n * MIN;
  const marcoFirst = (score: number, reason: string): MockCandidate[] => [
    { contractor_id: CONTRACTOR.marco, match_score: score, match_reason: reason, state: 'OFFERED' },
    {
      contractor_id: CONTRACTOR.ana,
      match_score: score - 0.1,
      match_reason: 'Available, 6 mi away',
      state: 'QUEUED',
    },
  ];
  const wo = (
    w: Partial<MockWorkOrder> & Pick<MockWorkOrder, 'wo_id' | 'asset_id' | 'symptom'>,
  ): MockWorkOrder => ({
    tenant_id: TENANT.midtown,
    state: 'PENDING',
    current_contractor_id: CONTRACTOR.marco,
    sla_minutes: 15,
    sla_deadline: null,
    candidates: marcoFirst(0.91, 'RTU specialist, 2 mi away'),
    events: [],
    photos: [],
    decline: null,
    completion: null,
    predicted_failure_code: w.asset_id === ASSET.rtu04 ? 'COMP-CONTACTOR' : null,
    ...w,
  });
  const advanced = (stage: S['LifecycleStage'], at: number, n: number): S['LifecycleEvent'] => ({
    event_id: uid(0x600 + n),
    type: 'ADVANCE',
    stage,
    corrects_event_id: null,
    actor_user_id: uid(0x300),
    at: new Date(at).toISOString(),
  });
  const bound = (score: number): MockCandidate[] => [
    {
      contractor_id: CONTRACTOR.marco,
      match_score: score,
      match_reason: 'Assigned crew',
      state: 'ACCEPTED',
    },
  ];
  return {
    now,
    users: users(),
    assets: assets(t),
    failureCodes: FAILURE_CODES,
    idempotency: new Map(),
    seq: 0,
    workorders: [
      wo({
        wo_id: WO.rtu12m,
        asset_id: ASSET.rtu04,
        symptom: 'Not cooling; tenants on 32 report 81°F',
        sla_deadline: m(12),
      }),
      wo({
        wo_id: WO.ahu4m,
        asset_id: ASSET.ahuNew01,
        symptom: 'Rattling noise from supply fan',
        sla_deadline: m(4),
        candidates: marcoFirst(0.78, 'AHU certified, 3 mi away'),
      }),
      wo({
        wo_id: WO.rtu45s,
        asset_id: ASSET.rtu04,
        symptom: 'Compressor tripping breaker',
        sla_deadline: t + 45_000,
      }),
      wo({
        wo_id: WO.ahuPast,
        asset_id: ASSET.ahuNew01,
        symptom: 'Low airflow in lobby',
        sla_deadline: t - 30_000,
      }),
      wo({
        wo_id: WO.accepted,
        asset_id: ASSET.ahuNew01,
        symptom: 'Filter alarm',
        state: 'ACCEPTED',
        candidates: bound(0.8),
      }),
      wo({
        wo_id: WO.arrived,
        asset_id: ASSET.rtu04,
        symptom: 'Unit short-cycling',
        state: 'IN_PROGRESS',
        candidates: bound(0.93),
        events: [advanced('EN_ROUTE', m(-40), 1), advanced('ARRIVED', m(-10), 2)],
      }),
      wo({
        wo_id: WO.anaOffer,
        asset_id: ASSET.rtu04,
        symptom: 'Thermostat unresponsive on 30',
        current_contractor_id: CONTRACTOR.ana,
        sla_deadline: m(10),
        candidates: [
          {
            contractor_id: CONTRACTOR.ana,
            match_score: 0.88,
            match_reason: 'On site nearby',
            state: 'OFFERED',
          },
          {
            contractor_id: CONTRACTOR.marco,
            match_score: 0.8,
            match_reason: 'RTU specialist',
            state: 'QUEUED',
          },
        ],
      }),
      wo({
        wo_id: WO.zedOffer,
        tenant_id: TENANT.other,
        asset_id: ASSET.zedRtu,
        symptom: 'No heat',
        current_contractor_id: CONTRACTOR.zed,
        sla_deadline: m(20),
        candidates: [
          {
            contractor_id: CONTRACTOR.zed,
            match_score: 0.9,
            match_reason: 'Only crew',
            state: 'OFFERED',
          },
        ],
      }),
    ],
  };
}
