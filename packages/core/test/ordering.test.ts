import { describe, expect, it } from 'vitest';
import { sortActive, sortOffers } from '../src/index';

const at = (min: number) => new Date(Date.UTC(2026, 10, 2, 15, min)).toISOString();

describe('T-INBOX-1 ordering (core slice)', () => {
  it('sorts offers by soonest sla_deadline first', () => {
    const offers = [
      { wo_id: 'wo-12m', sla_deadline: at(12) },
      { wo_id: 'wo-45s', sla_deadline: at(1) },
      { wo_id: 'wo-past', sla_deadline: at(-3) },
      { wo_id: 'wo-4m', sla_deadline: at(4) },
    ];
    expect(sortOffers(offers).map((o) => o.wo_id)).toEqual([
      'wo-past',
      'wo-45s',
      'wo-4m',
      'wo-12m',
    ]);
  });

  it('sorts active jobs by most recently advanced first', () => {
    const active = [
      { wo_id: 'accepted', last_advanced_at: at(0) },
      { wo_id: 'arrived', last_advanced_at: at(20) },
      { wo_id: 'en-route', last_advanced_at: at(10) },
    ];
    expect(sortActive(active).map((o) => o.wo_id)).toEqual(['arrived', 'en-route', 'accepted']);
  });

  it('puts items without a (valid) timestamp last, and breaks ties by wo_id for stability', () => {
    const offers = [
      { wo_id: 'c' },
      { wo_id: 'b', sla_deadline: at(5) },
      { wo_id: 'z', sla_deadline: null },
      { wo_id: 'a', sla_deadline: at(5) },
      { wo_id: 'y', sla_deadline: 'garbage' },
    ];
    expect(sortOffers(offers).map((o) => o.wo_id)).toEqual(['a', 'b', 'c', 'y', 'z']);
    const active = [
      { wo_id: 'q', last_advanced_at: null },
      { wo_id: 'p', last_advanced_at: at(1) },
      { wo_id: 'o', last_advanced_at: at(1) },
      { wo_id: 'n' },
    ];
    expect(sortActive(active).map((o) => o.wo_id)).toEqual(['o', 'p', 'n', 'q']);
  });

  it('compares instants, not strings (mixed offsets)', () => {
    const offers = [
      { wo_id: 'later', sla_deadline: '2026-11-02T10:10:00-05:00' }, // 15:10Z
      { wo_id: 'sooner', sla_deadline: '2026-11-02T15:05:00Z' },
    ];
    expect(sortOffers(offers).map((o) => o.wo_id)).toEqual(['sooner', 'later']);
  });

  it('does not mutate its input and keeps extra fields', () => {
    const input = [
      { wo_id: 'b', sla_deadline: at(2), extra: 1 },
      { wo_id: 'a', sla_deadline: at(1), extra: 2 },
    ];
    const copy = structuredClone(input);
    const out = sortOffers(input);
    expect(input).toEqual(copy);
    expect(out).not.toBe(input);
    expect(out[0]).toBe(input[1]);
  });
});
