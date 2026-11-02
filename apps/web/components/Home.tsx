import type { ApiStatus } from '@/lib/api-status';
import type { DataSource } from '@/lib/config';

const API_LABEL: Record<ApiStatus, string> = {
  mock: 'Contract mock',
  reachable: 'API connected',
  unreachable: 'API unreachable',
};

export interface HomeProps {
  dataSource: DataSource;
  apiStatus: ApiStatus;
}

/** M0 placeholder screen. Replaced by the Offer Inbox in M4. */
export function Home({ dataSource, apiStatus }: HomeProps) {
  return (
    <main className="home">
      <h1 className="home__title">InsmartFix</h1>
      <p className="home__lede">Contractor field app — scaffold.</p>
      <dl className="home__meta">
        <dt>Data source</dt>
        <dd data-testid="data-source">{dataSource}</dd>
        <dt>Backend</dt>
        <dd data-testid="api-status">{API_LABEL[apiStatus]}</dd>
      </dl>
    </main>
  );
}
