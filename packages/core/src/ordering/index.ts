/**
 * Inbox ordering (FR-2.2, design §6.2, T-INBOX-1): offers by soonest `sla_deadline`; active jobs
 * by most recent `last_advanced_at`. Items without a valid timestamp go last; ties break on
 * `wo_id` so the list never reshuffles between refreshes. Inputs are never mutated.
 */

interface Identified {
  wo_id: string;
}

const instant = (iso: string | null | undefined): number | null => {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : t;
};

function sortBy<T extends Identified>(
  items: readonly T[],
  key: (item: T) => string | null | undefined,
  direction: 1 | -1,
): T[] {
  return items
    .map((item) => ({ item, t: instant(key(item)) }))
    .sort((a, b) => {
      if (a.t !== b.t) {
        if (a.t === null) return 1;
        if (b.t === null) return -1;
        return (a.t - b.t) * direction;
      }
      return a.item.wo_id < b.item.wo_id ? -1 : a.item.wo_id > b.item.wo_id ? 1 : 0;
    })
    .map(({ item }) => item);
}

export function sortOffers<T extends Identified & { sla_deadline?: string | null }>(
  offers: readonly T[],
): T[] {
  return sortBy(offers, (o) => o.sla_deadline, 1);
}

export function sortActive<T extends Identified & { last_advanced_at?: string | null }>(
  active: readonly T[],
): T[] {
  return sortBy(active, (o) => o.last_advanced_at, -1);
}
