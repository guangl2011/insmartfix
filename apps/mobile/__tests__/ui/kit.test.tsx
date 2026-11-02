import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { brand, getTheme } from '@insmartfix/tokens';
import { ThemeProvider } from '../../src/theme';
import {
  AppText,
  Banner,
  Button,
  dispatchLabel,
  EmptyState,
  ErrorState,
  HealthScore,
  PRIMARY_ACTION_TESTID,
  RiskBadge,
  riskLabel,
  Sheet,
  Skeleton,
  SkeletonCard,
  StatusChip,
  Toast,
} from '../../src/ui';
import {
  brandFills,
  ergonomicsViolations,
  statusColorLeaks,
  statusColorUses,
} from '../helpers/ergo';

type Mode = 'light' | 'dark';
const MODES: Mode[] = ['light', 'dark'];

function Kit({
  onPress = () => {},
  onDismiss = () => {},
}: {
  onPress?: () => void;
  onDismiss?: () => void;
}) {
  return (
    <>
      <Button label="Accept" variant="primary" onPress={onPress} />
      <Button label="Decline" onPress={onPress} testID="decline" />
      <Button label="Skip" variant="quiet" onPress={onPress} testID="skip" />
      <StatusChip label="En route" />
      <StatusChip label="Accepted" tone="brand" />
      <HealthScore score={44} size="full" testID="health" />
      <RiskBadge risk="HIGH" testID="risk" />
      <EmptyState
        title="Offers"
        message="No open offers right now. We'll show new dispatch here the moment it arrives."
      />
      <ErrorState message="Couldn't load your jobs" onRetry={onPress} />
      <Skeleton testID="skeleton" />
      <SkeletonCard />
      <Banner message="You're offline — showing your last update" />
      <Toast message="This offer just expired — it's been reassigned" onHide={onDismiss} />
      <Sheet visible title="Decline offer?" onDismiss={onDismiss}>
        <AppText>Optional reason</AppText>
      </Sheet>
    </>
  );
}

const renderIn = (mode: Mode, ui = <Kit />) =>
  render(<ThemeProvider mode={mode}>{ui}</ThemeProvider>);

describe('mobile UI kit (M5-T1)', () => {
  it.each(MODES)(
    'T-ERGO-1 every primitive has ≥ 44 pt targets and ≥ 16 pt text (%s)',
    async (mode) => {
      await renderIn(mode);
      expect(ergonomicsViolations(screen.container)).toEqual([]);
    },
  );

  it.each(MODES)(
    'T-THEME-1 status color appears only inside HealthScore and RiskBadge (%s)',
    async (mode) => {
      await renderIn(mode);
      expect(statusColorLeaks(screen.container)).toEqual([]);
      // …and those two components do use it (band solid, risk pill fill + text).
      expect(statusColorUses(screen.container).length).toBeGreaterThanOrEqual(3);
    },
  );

  it('T-THEME-1 the primary button is the only brand-teal fill in the kit', async () => {
    await renderIn('light');
    expect(screen.getAllByTestId(PRIMARY_ACTION_TESTID)).toHaveLength(1);
    expect(brandFills(screen.container, brand.primary)).toHaveLength(1);
  });

  it('renders the primary button with white action text on the brand fill', async () => {
    await renderIn('dark', <Button label="Sign in" variant="primary" onPress={() => {}} />);
    const btn = screen.getByRole('button', { name: 'Sign in' });
    expect(btn).toHaveStyle({ backgroundColor: brand.primary, minHeight: 48 });
    expect(screen.getByText('Sign in')).toHaveStyle({
      color: '#FFFFFF',
      fontSize: 19,
      fontWeight: '700',
    });
  });

  it('presses, and a busy or disabled button does not', async () => {
    const onPress = jest.fn();
    await renderIn('light', <Button label="Accept" variant="primary" onPress={onPress} />);
    await fireEvent.press(screen.getByRole('button', { name: 'Accept' }));
    expect(onPress).toHaveBeenCalledTimes(1);

    await screen.rerender(
      <ThemeProvider mode="light">
        <Button label="Accepting…" variant="primary" busy onPress={onPress} />
      </ThemeProvider>,
    );
    const busy = screen.getByRole('button', { name: 'Accepting…' });
    expect(busy).toBeDisabled();
    expect(busy).toBeBusy();
    await fireEvent.press(busy);

    await screen.rerender(
      <ThemeProvider mode="light">
        <Button label="Sign in" variant="primary" disabled onPress={onPress} />
      </ThemeProvider>,
    );
    await fireEvent.press(screen.getByRole('button', { name: 'Sign in' }));
    expect(onPress).toHaveBeenCalledTimes(1);
  });

  it('T-A11Y-2 labels the health score, risk badge and status pill for screen readers', async () => {
    await renderIn('light');
    expect(screen.getByLabelText('Health score 44 of 100, High')).toBeOnTheScreen();
    expect(screen.getByLabelText('Failure risk: High risk')).toBeOnTheScreen();
    expect(screen.getByLabelText('Status: En route')).toBeOnTheScreen();
    expect(screen.getByText('Health 44')).toBeOnTheScreen();
    expect(screen.getByText('High risk')).toBeOnTheScreen();
  });

  it.each([
    [92, 'Healthy'],
    [65, 'Medium'],
    [44, 'High'],
    [12, 'Critical'],
  ])('HealthScore %i reads as %s (number + label, never color alone)', async (score, band) => {
    await renderIn('light', <HealthScore score={score} size="full" />);
    expect(screen.getByText(`Health ${score}`)).toBeOnTheScreen();
    expect(screen.getByText(band)).toBeOnTheScreen();
  });

  it('labels every risk band', () => {
    expect(['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].map((r) => riskLabel(r as 'LOW'))).toEqual([
      'Low risk',
      'Medium risk',
      'High risk',
      'Critical risk',
    ]);
  });

  it('maps dispatch states and lifecycle stages to neutral pill copy', () => {
    expect(dispatchLabel('PENDING')).toBe('Pending');
    expect(dispatchLabel('IN_PROGRESS', 'ARRIVED')).toBe('Arrived');
    expect(dispatchLabel('ACCEPTED', null)).toBe('Accepted');
    expect(dispatchLabel('COMPLETED', 'ARRIVED')).toBe('Completed');
    expect(dispatchLabel('NO_CONTRACTORS')).toBe('No contractors');
    expect(dispatchLabel('SOMETHING_NEW')).toBe('SOMETHING_NEW');
  });

  it('T-INBOX-7 the skeleton is a labelled busy placeholder, not a spinner', async () => {
    await renderIn('light', <Skeleton testID="skeleton" lines={2} />);
    const s = screen.getByTestId('skeleton');
    expect(s).toHaveAccessibleName('Loading');
    expect(s).toBeBusy();
    expect(screen.container.queryAll((n) => n.type === 'ActivityIndicator')).toHaveLength(0);
  });

  it('ErrorState offers Retry as a neutral secondary action', async () => {
    const retry = jest.fn();
    await renderIn('light', <ErrorState message="Couldn't load this job" onRetry={retry} />);
    expect(screen.getByRole('alert')).toHaveTextContent("Couldn't load this job");
    expect(screen.queryByTestId(PRIMARY_ACTION_TESTID)).toBeNull();
    await fireEvent.press(screen.getByRole('button', { name: 'Retry' }));
    expect(retry).toHaveBeenCalled();
  });

  it('Toast announces, then hides itself after its duration', async () => {
    jest.useFakeTimers();
    try {
      const onHide = jest.fn();
      await renderIn('light', <Toast message="Saved" onHide={onHide} durationMs={1000} />);
      expect(screen.getByRole('alert')).toHaveAccessibleName('Saved');
      await act(() => jest.advanceTimersByTime(999));
      expect(onHide).not.toHaveBeenCalled();
      await act(() => jest.advanceTimersByTime(1));
      expect(onHide).toHaveBeenCalledTimes(1);
      await screen.rerender(
        <ThemeProvider mode="light">
          <Toast message={null} onHide={onHide} />
        </ThemeProvider>,
      );
      expect(screen.queryByRole('alert')).toBeNull();
    } finally {
      jest.useRealTimers();
    }
  });

  it('Sheet is dismissible from the backdrop and the Close button (no modal trap)', async () => {
    const onDismiss = jest.fn();
    await renderIn(
      'light',
      <Sheet visible title="Decline offer?" onDismiss={onDismiss}>
        <AppText>Reason</AppText>
      </Sheet>,
    );
    expect(screen.getByRole('header', { name: 'Decline offer?' })).toBeOnTheScreen();
    // The panel is accessibilityViewIsModal, so the backdrop is hidden from screen readers (Close covers it).
    await fireEvent.press(screen.getByTestId('sheet-backdrop', { includeHiddenElements: true }));
    await fireEvent.press(screen.getByTestId('sheet-close'));
    expect(onDismiss).toHaveBeenCalledTimes(2);
  });

  it('Banner is a polite live region with the offline copy', async () => {
    await renderIn(
      'light',
      <Banner message="You're offline — showing your last update" testID="offline" />,
    );
    expect(screen.getByTestId('offline')).toHaveAccessibleName(
      "You're offline — showing your last update",
    );
  });

  it.each(MODES)('NFR-9 uses the %s neutral surfaces from the tokens', async (mode) => {
    await renderIn(mode, <EmptyState message="Nothing here" testID="empty" />);
    expect(screen.getByTestId('empty')).toHaveStyle({
      backgroundColor: getTheme(mode).colors.surface2,
    });
  });
});
