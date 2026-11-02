/**
 * Session state for the mobile app (FR-1.1, FR-1.3, FR-1.4). The bearer token is read from the
 * secure store into memory only; API calls go to `/v1/me/*` (the server resolves the contractor
 * from the token — the app never sends a contractor id). Any 401 on an authenticated call ends
 * the session and returns the user to /login.
 */
import { apiErrorInfo, type ApiClient } from '@insmartfix/contracts';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { useServices } from '../data';
import {
  createSecureTokenStore,
  isUnexpired,
  type StoredSession,
  type TokenStore,
  type UserProfile,
} from './tokenStore';

export type SessionStatus = 'loading' | 'signedOut' | 'signedIn';

export type SignInResult =
  { ok: true } | { ok: false; reason: 'invalid' | 'rate_limited' | 'network' | 'server' };

export interface Session {
  status: SessionStatus;
  user: UserProfile | null;
  /** Authenticated typed client; a 401 response signs the user out. */
  api: ApiClient;
  signIn(email: string, password: string): Promise<SignInResult>;
  /** Clears the local session (the full sign-out with logout + wipe is in the Account screen). */
  endSession(): Promise<void>;
}

/** Token + 401 hook shared with the API client outside React's render data. */
function createTokenBox() {
  let token: string | null = null;
  let handler: () => void = () => {};
  return {
    get: () => token,
    set: (t: string | null) => {
      token = t;
    },
    onUnauthorized: (h: () => void) => {
      handler = h;
    },
    unauthorized: () => handler(),
  };
}

const SessionContext = createContext<Session | null>(null);

export interface SessionProviderProps {
  children: ReactNode;
  tokenStore?: TokenStore;
}

export function SessionProvider({ children, tokenStore }: SessionProviderProps) {
  const services = useServices();
  const store = useMemo(() => tokenStore ?? createSecureTokenStore(), [tokenStore]);
  const [session, setSession] = useState<StoredSession | null>(null);
  const [status, setStatus] = useState<SessionStatus>('loading');
  // The in-memory copy of the token used by the client (never persisted anywhere else), and the
  // hook the client calls on a 401. Plain mutable state shared with the client, not render data.
  const [box] = useState(createTokenBox);

  const endSession = useCallback(async () => {
    box.set(null);
    setSession(null);
    setStatus('signedOut');
    await store.clear().catch(() => {});
  }, [store, box]);

  useEffect(() => {
    box.onUnauthorized(() => void endSession());
  }, [box, endSession]);

  useEffect(() => {
    let live = true;
    store
      .load()
      .catch(() => null)
      .then((s) => {
        if (!live) return;
        if (s && isUnexpired(s, Date.now())) {
          box.set(s.access_token);
          setSession(s);
          setStatus('signedIn');
        } else {
          if (s) store.clear().catch(() => {});
          setStatus('signedOut');
        }
      });
    return () => {
      live = false;
    };
  }, [store, box]);

  const api = useMemo(() => {
    const client = services.createClient(box.get);
    client.use({
      onResponse({ request, response }) {
        // Only an authenticated call can end the session (a failed login is just a 401 too).
        if (response.status === 401 && request.headers.has('Authorization')) box.unauthorized();
        return undefined;
      },
    });
    return client;
  }, [services, box]);

  const signIn = useCallback(
    async (email: string, password: string): Promise<SignInResult> => {
      let res;
      try {
        res = await api.POST('/v1/auth/login', { body: { email: email.trim(), password } });
      } catch {
        return { ok: false, reason: 'network' };
      }
      if (res.data) {
        const s: StoredSession = {
          access_token: res.data.access_token,
          expires_at: res.data.expires_at,
          user: res.data.user,
        };
        await store.save(s);
        box.set(s.access_token);
        setSession(s);
        setStatus('signedIn');
        return { ok: true };
      }
      const { code } = apiErrorInfo(res.error);
      if (res.response.status === 401 || code === 'INVALID_CREDENTIALS')
        return { ok: false, reason: 'invalid' };
      if (res.response.status === 429) return { ok: false, reason: 'rate_limited' };
      return { ok: false, reason: 'server' };
    },
    [api, store, box],
  );

  const value = useMemo<Session>(
    () => ({ status, user: session?.user ?? null, api, signIn, endSession }),
    [status, session, api, signIn, endSession],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): Session {
  const s = useContext(SessionContext);
  if (!s) throw new Error('useSession() outside <SessionProvider>');
  return s;
}
