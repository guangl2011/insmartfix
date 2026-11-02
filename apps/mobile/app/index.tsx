import { Redirect } from 'expo-router';
import { useSession } from '@/src/auth';

/** `/` → the Inbox when signed in (design §5), otherwise Login. */
export default function Index() {
  const { status } = useSession();
  if (status === 'loading') return null;
  return <Redirect href={status === 'signedIn' ? '/inbox' : '/login'} />;
}
