import { Redirect } from 'expo-router';

/** `/` → the Inbox, the home screen (design §5). */
export default function Index() {
  return <Redirect href="/inbox" />;
}
