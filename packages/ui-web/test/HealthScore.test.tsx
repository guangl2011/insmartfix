import { render, screen } from '@testing-library/react';
import { HealthScore } from '../src';
import { axeViolations } from './axe';

describe('HealthScore (status color, always labeled)', () => {
  it.each([
    [92, 'healthy', 'Healthy'],
    [65, 'medium', 'Medium'],
    [44, 'high', 'High'],
    [12, 'critical', 'Critical'],
  ])('score %i → %s band with its label', async (score, band, label) => {
    const { container } = render(<HealthScore score={score} size="full" />);
    const el = screen.getByRole('img', { name: `Health score ${score} of 100, ${label}` });
    expect(el).toHaveAttribute('data-band', band);
    expect(screen.getByText(`Health ${score}`)).toBeInTheDocument();
    expect(screen.getByText(label)).toBeInTheDocument();
    // The band color is a bar beside the number; the number itself is a neutral text role.
    expect(screen.getByTestId('health-band').style.backgroundColor).toBe(`var(--status-${band})`);
    expect(screen.getByText(`Health ${score}`).className).toContain('text-primary');
    expect(await axeViolations(container)).toEqual([]);
  });

  it('inline size omits the band label; clamps and rounds the score', () => {
    render(<HealthScore score={120.4} />);
    expect(screen.getByRole('img', { name: 'Health score 100 of 100, Healthy' })).toBeTruthy();
    expect(screen.queryByText('Healthy')).toBeNull();
  });
});
