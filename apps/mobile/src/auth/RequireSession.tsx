import { Redirect } from 'expo-router';
import type { ReactNode } from 'react';
import { useSession } from './session';

/** Signed-in routes: nothing renders until the session is known; signed out → /login. */
export function RequireSession({ children }: { children: ReactNode }) {
  const { status } = useSession();
  if (status === 'loading') return null;
  if (status === 'signedOut') return <Redirect href="/login" />;
  return <>{children}</>;
}
