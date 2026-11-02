import { Home } from '@/components/Home';
import { probeApi } from '@/lib/api-status';
import { getServerConfig } from '@/lib/config';

export const dynamic = 'force-dynamic';

export default async function HomePage() {
  const config = getServerConfig();
  const apiStatus = await probeApi(config);
  return <Home dataSource={config.dataSource} apiStatus={apiStatus} />;
}
