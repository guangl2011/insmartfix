import { describe, expect, it } from 'vitest';
import {
  COMPLETION_LIMITS,
  emptyCompletionDraft,
  orderFailureCodes,
  toCompletionReport,
  validateCompletion,
} from '../src';
import type { CompletionDraft, FailureCode } from '../src';

const CATALOG: FailureCode[] = [
  {
    code: 'RTU-CONT',
    subtype: 'RTU',
    component_group: 'electrical',
    label: 'Compressor contactor',
  },
  { code: 'RTU-CAP', subtype: 'RTU', component_group: 'electrical', label: 'Run capacitor' },
  { code: 'RTU-BELT', subtype: 'RTU', component_group: 'airflow', label: 'Blower belt' },
  { code: 'AHU-FILT', subtype: 'AHU', component_group: 'airflow', label: 'Clogged filter' },
  { code: 'RTU-REF', subtype: 'RTU', component_group: 'refrigerant', label: 'Réfrigérant leak' },
];

const valid = (over: Partial<CompletionDraft> = {}): CompletionDraft => ({
  ...emptyCompletionDraft('Marco Rossi'),
  failure_code: 'RTU-CONT',
  actual_fault_matched: true,
  labor_hours: 1.5,
  ...over,
});

const errs = (d: CompletionDraft, catalog = CATALOG) =>
  Object.fromEntries(
    Object.entries(validateCompletion(d, catalog).errors).map(([k, v]) => [k, v.code]),
  );

describe('validateCompletion (FR-7.1)', () => {
  it('T-COMP-1 a complete draft is valid', () => {
    expect(validateCompletion(valid(), CATALOG)).toEqual({ valid: true, errors: {} });
  });

  it('T-COMP-1 an empty draft reports every required field', () => {
    const r = validateCompletion(emptyCompletionDraft(), CATALOG);
    expect(r.valid).toBe(false);
    expect(errs(emptyCompletionDraft())).toEqual({
      failure_code: 'required',
      actual_fault_matched: 'required',
      labor_hours: 'required',
      technician_id: 'required',
    });
    expect(r.errors.failure_code?.message).toBe('Choose the failure code you found.');
  });

  it('T-COMP-1 failure code must be from the catalog when the catalog is loaded', () => {
    expect(errs(valid({ failure_code: 'NOPE' }))).toEqual({ failure_code: 'unknown_code' });
    expect(errs(valid({ failure_code: 'NOPE' }), [])).toEqual({});
    expect(errs(valid({ failure_code: '   ' }))).toEqual({ failure_code: 'required' });
    expect(errs(valid({ failure_code: 'X'.repeat(65) }))).toEqual({ failure_code: 'too_long' });
  });

  it('T-COMP-1 matched toggle is required (false is an answer)', () => {
    expect(errs(valid({ actual_fault_matched: false }))).toEqual({});
    expect(errs(valid({ actual_fault_matched: null }))).toEqual({
      actual_fault_matched: 'required',
    });
  });

  it.each([
    [0.25, null],
    [24, null],
    [7.75, null],
    [0, 'out_of_range'],
    [-1, 'out_of_range'],
    [24.25, 'out_of_range'],
    [Infinity, 'out_of_range'],
    [1.1, 'step'],
    [0.3, 'step'],
    [NaN, 'required'],
    [null, 'required'],
  ])('T-COMP-1 labor hours %s → %s', (h, expected) => {
    expect(errs(valid({ labor_hours: h })).labor_hours ?? null).toBe(expected);
  });

  it('T-COMP-1 notes, photos and technician bounds', () => {
    const max = COMPLETION_LIMITS.notesMax;
    expect(errs(valid({ notes: 'n'.repeat(max) }))).toEqual({});
    expect(errs(valid({ notes: 'n'.repeat(max + 1) }))).toEqual({ notes: 'too_long' });
    const photos = (n: number) => Array.from({ length: n }, (_, i) => ({ local_id: `p${i}` }));
    expect(errs(valid({ photos: photos(4) }))).toEqual({});
    expect(errs(valid({ photos: photos(5) }))).toEqual({ photos: 'too_many' });
    expect(errs(valid({ technician_id: ' ' }))).toEqual({ technician_id: 'required' });
    expect(errs(valid({ technician_id: 't'.repeat(121) }))).toEqual({ technician_id: 'too_long' });
  });

  it('T-COMP-1 part rows are checked per row', () => {
    const d = valid({
      parts_used: [
        { description: 'Contactor 40A', qty: 1, part_code: 'C-40' },
        { description: ' ', qty: 0 },
        { description: 'd'.repeat(201), qty: 1.5, part_code: 'p'.repeat(65) },
        { description: 'ok', qty: 1000 },
      ],
    });
    expect(errs(d)).toEqual({
      'parts_used.1.description': 'required',
      'parts_used.1.qty': 'out_of_range',
      'parts_used.2.description': 'too_long',
      'parts_used.2.qty': 'out_of_range',
      'parts_used.2.part_code': 'too_long',
      'parts_used.3.qty': 'out_of_range',
    });
    const many = Array.from({ length: 51 }, () => ({ description: 'x', qty: 1 }));
    expect(errs(valid({ parts_used: many }))).toEqual({ parts_used: 'too_many' });
  });
});

describe('toCompletionReport', () => {
  it('builds the trimmed request body with the given photo ids', () => {
    const d = valid({
      failure_code: ' RTU-CONT ',
      notes: '  pitted contacts ',
      parts_used: [
        { description: ' Contactor ', qty: 1, part_code: ' C-40 ' },
        { description: 'Wire nut', qty: 3, part_code: '  ' },
      ],
      photos: [{ local_id: 'a' }],
    });
    expect(toCompletionReport(d, ['ph-1'])).toEqual({
      failure_code: 'RTU-CONT',
      actual_fault_matched: true,
      parts_used: [
        { part_code: 'C-40', description: 'Contactor', qty: 1 },
        { description: 'Wire nut', qty: 3 },
      ],
      labor_hours: 1.5,
      notes: 'pitted contacts',
      technician_id: 'Marco Rossi',
      photo_ids: ['ph-1'],
    });
    expect(toCompletionReport(valid({ notes: '   ' }), [])).not.toHaveProperty('notes');
  });

  it('refuses an invalid draft', () => {
    expect(() => toCompletionReport(emptyCompletionDraft(), [])).toThrow(/failure_code/);
  });
});

describe('orderFailureCodes (FR-7.1)', () => {
  const codes = (o: { code: string }[]) => o.map((c) => c.code);

  it('T-COMP-2 predicted code is offered first as "Confirm: …", filtered by subtype', () => {
    const opts = orderFailureCodes(CATALOG, 'RTU-CAP', 'RTU');
    expect(codes(opts)).toEqual(['RTU-CAP', 'RTU-CONT', 'RTU-BELT', 'RTU-REF']);
    expect(opts[0]).toMatchObject({ predicted: true, display: 'Confirm: Run capacitor' });
    expect(opts.slice(1).every((o) => !o.predicted && o.display === o.label)).toBe(true);
  });

  it('T-COMP-2 no prediction, or a prediction outside the subtype, offers no confirm row', () => {
    expect(orderFailureCodes(CATALOG, null, 'RTU').some((o) => o.predicted)).toBe(false);
    expect(orderFailureCodes(CATALOG, 'AHU-FILT', 'RTU').some((o) => o.predicted)).toBe(false);
    expect(codes(orderFailureCodes(CATALOG, undefined, null))).toHaveLength(5);
  });

  it('T-COMP-2 search matches code, label or group, every word, ignoring case and accents', () => {
    expect(codes(orderFailureCodes(CATALOG, 'RTU-CAP', 'RTU', 'ELECTRICAL'))).toEqual([
      'RTU-CAP',
      'RTU-CONT',
    ]);
    expect(codes(orderFailureCodes(CATALOG, 'RTU-CAP', 'RTU', 'compressor contact'))).toEqual([
      'RTU-CONT',
    ]);
    expect(codes(orderFailureCodes(CATALOG, null, 'RTU', 'refrigerant'))).toEqual(['RTU-REF']);
    expect(codes(orderFailureCodes(CATALOG, null, 'RTU', 'rtu-b'))).toEqual(['RTU-BELT']);
    expect(orderFailureCodes(CATALOG, null, 'RTU', 'zzz')).toEqual([]);
  });

  it('drops duplicate codes from the catalog', () => {
    const dup = [...CATALOG, { ...CATALOG[0]!, label: 'dup' }];
    expect(codes(orderFailureCodes(dup, null, 'RTU'))).toEqual([
      'RTU-CONT',
      'RTU-CAP',
      'RTU-BELT',
      'RTU-REF',
    ]);
  });
});
