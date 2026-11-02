/**
 * The session lives ONLY in the OS keychain / keystore via expo-secure-store (FR-1.3, T-AUTH-5):
 * never AsyncStorage, never logs. `THIS_DEVICE_ONLY` keeps it out of backups and device transfer.
 */
import * as SecureStore from 'expo-secure-store';
import type { components } from '@insmartfix/contracts';

export type UserProfile = components['schemas']['UserProfile'];

export interface StoredSession {
  access_token: string;
  /** ISO-8601; the session is treated as signed out after this instant. */
  expires_at: string;
  user: UserProfile;
}

export const SESSION_KEY = 'ifx.session';
const OPTIONS: SecureStore.SecureStoreOptions = {
  keychainAccessible: SecureStore.AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY,
};

export interface TokenStore {
  load(): Promise<StoredSession | null>;
  save(session: StoredSession): Promise<void>;
  clear(): Promise<void>;
}

function isSession(v: unknown): v is StoredSession {
  const s = v as Partial<StoredSession> | null;
  return (
    !!s &&
    typeof s.access_token === 'string' &&
    typeof s.expires_at === 'string' &&
    typeof s.user === 'object' &&
    s.user !== null &&
    typeof s.user.user_id === 'string'
  );
}

export function createSecureTokenStore(store: typeof SecureStore = SecureStore): TokenStore {
  return {
    async load() {
      const raw = await store.getItemAsync(SESSION_KEY, OPTIONS);
      if (!raw) return null;
      try {
        const parsed: unknown = JSON.parse(raw);
        return isSession(parsed) ? parsed : null;
      } catch {
        return null;
      }
    },
    save: (session) => store.setItemAsync(SESSION_KEY, JSON.stringify(session), OPTIONS),
    clear: () => store.deleteItemAsync(SESSION_KEY, OPTIONS),
  };
}

/** True while the token is still within its `expires_at` (device clock; the server is final). */
export function isUnexpired(session: StoredSession, nowMs: number): boolean {
  const t = Date.parse(session.expires_at);
  return Number.isFinite(t) && t > nowMs;
}
