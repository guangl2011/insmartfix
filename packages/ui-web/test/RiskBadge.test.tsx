import { render, screen } from '@testing-library/react';
import { RiskBadge, riskLabel } from '../src';
import { axeViolations } from './axe';

describe('RiskBadge (status color, always labeled)', () => {
  it.each([
    ['LOW', 'healthy', 'Low risk'],
    ['MEDIUM', 'medium', 'Medium risk'],
    ['HIGH', 'high', 'High risk'],
    ['CRITICAL', 'critical', 'Critical risk'],
  ] as const)('%s → %s pill reading "%s"', async (risk, band, label) => {
    const { container } = render(<RiskBadge risk={risk} />);
    const pill = screen.getByText(label);
    expect(pill).toHaveTextContent(`Failure risk: ${label}`);
    expect(pill).toHaveAttribute('data-band', band);
    expect(pill.style.backgroundColor).toBe(`var(--status-${band}-bg)`);
    expect(pill.style.color).toBe(`var(--status-${band}-fg)`);
    expect(riskLabel(risk)).toBe(label);
    expect(await axeViolations(container)).toEqual([]);
  });
});
