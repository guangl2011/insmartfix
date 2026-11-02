/**
 * `Idempotency-Key` helpers (spec §5, D12). One key per logical mutation, generated once and
 * reused on every retry of that mutation (the offline queue stores it with the item). A new
 * body needs a new key: reusing one with a different body returns 422 IDEMPOTENCY_KEY_REUSED.
 */

export const IDEMPOTENCY_HEADER = 'Idempotency-Key';
/** The contract's header pattern. */
export const IDEMPOTENCY_KEY_PATTERN = /^[A-Za-z0-9._:-]{8,128}$/;

interface CryptoLike {
  randomUUID?: () => string;
  getRandomValues?: <T extends Uint8Array>(array: T) => T;
}

/** A UUIDv4 from the platform CSPRNG. Throws if none is available (never falls back to Math.random). */
export function newIdempotencyKey(
  crypto: CryptoLike | undefined = (globalThis as { crypto?: CryptoLike }).crypto,
): string {
  if (crypto?.randomUUID) return crypto.randomUUID();
  if (crypto?.getRandomValues) {
    const b = crypto.getRandomValues(new Uint8Array(16));
    b[6] = (b[6]! & 0x0f) | 0x40;
    b[8] = (b[8]! & 0x3f) | 0x80;
    const h = [...b].map((x) => x.toString(16).padStart(2, '0')).join('');
    return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
  }
  throw new Error('No secure random source for Idempotency-Key (polyfill crypto.getRandomValues)');
}

export function isValidIdempotencyKey(key: string): boolean {
  return IDEMPOTENCY_KEY_PATTERN.test(key);
}

/** `{ 'Idempotency-Key': key }` for `params.header`, validated against the contract pattern. */
export function idempotencyHeader(key: string): { 'Idempotency-Key': string } {
  if (!isValidIdempotencyKey(key))
    throw new Error('Idempotency-Key must match ' + IDEMPOTENCY_KEY_PATTERN);
  return { [IDEMPOTENCY_HEADER]: key } as { 'Idempotency-Key': string };
}
