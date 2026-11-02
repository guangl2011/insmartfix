import { render, screen } from '@testing-library/react';
import HomePage from './page';

describe('HomePage (server component)', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('renders mock mode without touching the API', async () => {
    vi.stubEnv('DATA_SOURCE', 'mock');
    render(await HomePage());
    expect(screen.getByTestId('api-status')).toHaveTextContent('Contract mock');
  });
});
