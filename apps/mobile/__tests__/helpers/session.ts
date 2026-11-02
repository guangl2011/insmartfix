/** Seeds the (mocked) keychain with a mock-backend session, as if the user had signed in. */
import { mockToken, type MockApi } from '@insmartfix/contracts/mocks';
import * as SecureStore from 'expo-secure-store';
import { SESSION_KEY } from '../../src/auth';

export const keychain = (SecureStore as unknown as { __store: Map<string, string> }).__store;

export function seedSession(
  mock: MockApi,
  email = 'marco@test.insmart.ai',
  expiresInMs = 12 * 3600_000,
) {
  const u = mock.db.users.find((x) => x.email === email)!;
  keychain.set(
    SESSION_KEY,
    JSON.stringify({
      access_token: mockToken(u),
      expires_at: new Date(Date.now() + expiresInMs).toISOString(),
      user: {
        user_id: u.user_id,
        name: u.name,
        role: u.role,
        tenant_id: u.tenant_id,
        contractor_id: u.contractor_id,
        company: u.company,
      },
    }),
  );
  return u;
}
