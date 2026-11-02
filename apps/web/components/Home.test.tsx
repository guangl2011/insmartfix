import { render, screen } from '@testing-library/react';
import { Home } from './Home';

describe('Home (M0 placeholder)', () => {
  it('renders the product name as the page heading', () => {
    render(<Home dataSource="live" apiStatus="reachable" />);
    expect(screen.getByRole('heading', { level: 1, name: 'InsmartFix' })).toBeInTheDocument();
    expect(screen.getByTestId('data-source')).toHaveTextContent('live');
    expect(screen.getByTestId('api-status')).toHaveTextContent('API connected');
  });

  it.each([
    ['mock', 'Contract mock'],
    ['unreachable', 'API unreachable'],
  ] as const)('labels api status %s', (status, label) => {
    render(<Home dataSource={status === 'mock' ? 'mock' : 'live'} apiStatus={status} />);
    expect(screen.getByTestId('api-status')).toHaveTextContent(label);
  });
});
