import * as React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  Banner,
  Button,
  EmptyState,
  ErrorState,
  HealthScore,
  RiskBadge,
  Sheet,
  Skeleton,
  SkeletonList,
  StatusChip,
  Toast,
  dispatchLabel,
  cx,
} from '../src';
import { axeViolations } from './axe';

describe('Button', () => {
  it('primary is the brand action with the large action label (contrast rule)', async () => {
    const onClick = vi.fn();
    const { container } = render(
      <Button variant="primary" onClick={onClick}>
        Accept
      </Button>,
    );
    const b = screen.getByRole('button', { name: 'Accept' });
    expect(b).toHaveAttribute('data-variant', 'primary');
    expect(b.className).toContain('bg-brand');
    expect(b.className).toContain('text-action');
    expect(b).toHaveAttribute('type', 'button');
    await userEvent.click(b);
    expect(onClick).toHaveBeenCalledOnce();
    expect(await axeViolations(container)).toEqual([]);
  });

  it('defaults to a neutral secondary button', () => {
    render(<Button>Decline</Button>);
    const b = screen.getByRole('button', { name: 'Decline' });
    expect(b).toHaveAttribute('data-variant', 'secondary');
    expect(b.className).not.toContain('bg-brand');
  });

  it('busy shows a spinner, the busy label, aria-busy and blocks clicks', async () => {
    const onClick = vi.fn();
    render(
      <Button variant="primary" busy busyLabel="Accepting…" onClick={onClick}>
        Accept
      </Button>,
    );
    const b = screen.getByRole('button', { name: 'Accepting…' });
    expect(b).toBeDisabled();
    expect(b).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByTestId('spinner')).toBeInTheDocument();
    await userEvent.click(b);
    expect(onClick).not.toHaveBeenCalled();
  });

  it('busy without a busy label keeps the label; block and quiet variants', () => {
    render(
      <>
        <Button busy>Sign in</Button>
        <Button variant="quiet" block className="extra">
          Skip
        </Button>
      </>,
    );
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeDisabled();
    const quiet = screen.getByRole('button', { name: 'Skip' });
    expect(quiet.className).toContain('w-full');
    expect(quiet.className).toContain('extra');
    expect(quiet).not.toHaveAttribute('aria-busy');
  });
});

describe('T-ERGO-1 (web primitives): tap targets ≥ 44 px, text ≥ 16 px', () => {
  it('every button primitive carries the 44 px minimum and the 48 px button height', () => {
    render(
      <>
        <Button variant="primary">A</Button>
        <Button>B</Button>
        <Button variant="quiet">C</Button>
        <Sheet open title="Decline" onDismiss={() => {}}>
          <p>x</p>
        </Sheet>
        <ErrorState message="Couldn't load your jobs" onRetry={() => {}} />
      </>,
    );
    for (const b of screen.getAllByRole('button')) {
      if (b.getAttribute('data-testid') === 'sheet-backdrop') continue; // full-screen
      expect(b.className).toMatch(/min-h-(tap|button)/);
      expect(b.className).toContain('min-w-tap');
    }
  });

  it('no primitive uses a text size below the token scale', () => {
    const { container } = render(
      <>
        <Button>B</Button>
        <StatusChip label="Pending" />
        <RiskBadge risk="HIGH" />
        <HealthScore score={44} size="full" />
        <EmptyState title="Nothing" message="No open offers right now." />
        <Banner message="You're offline" />
        <Toast message="Saved" onHide={() => {}} />
      </>,
    );
    expect(container.innerHTML).not.toMatch(/text-(xs|sm|\[1[0-5]px\])/);
  });
});

describe('StatusChip', () => {
  it('is neutral by default with a text label and screen-reader prefix', async () => {
    const { container } = render(<StatusChip label="En route" />);
    const chip = screen.getByText('En route');
    expect(chip).toHaveAttribute('data-tone', 'neutral');
    expect(chip).toHaveTextContent('Status: En route');
    expect(chip.className).not.toMatch(/status/);
    expect(await axeViolations(container)).toEqual([]);
  });

  it('brand tone uses the brand text role, never the brand fill', () => {
    render(<StatusChip label="Arrived" tone="brand" />);
    const chip = screen.getByText('Arrived');
    expect(chip.className).toContain('text-brand-text');
    expect(chip.className).not.toContain('bg-brand');
  });

  it('dispatchLabel maps states and lets the lifecycle stage win while in progress', () => {
    expect(dispatchLabel('PENDING')).toBe('Pending');
    expect(dispatchLabel('IN_PROGRESS', 'ARRIVED')).toBe('Arrived');
    expect(dispatchLabel('ACCEPTED', 'EN_ROUTE')).toBe('En route');
    expect(dispatchLabel('COMPLETED', 'ARRIVED')).toBe('Completed');
    expect(dispatchLabel('NO_CONTRACTORS', null)).toBe('No contractors');
    expect(dispatchLabel('SOMETHING_NEW')).toBe('SOMETHING_NEW');
  });
});

describe('EmptyState / ErrorState / Skeleton / Banner', () => {
  it('EmptyState renders the calm copy, an optional title and action', () => {
    render(
      <EmptyState
        data-testid="empty"
        title="Offers"
        message="No open offers right now. We'll show new dispatch here the moment it arrives."
        action={<Button>Refresh</Button>}
      />,
    );
    expect(screen.getByTestId('empty')).toHaveTextContent('No open offers right now.');
    expect(screen.getByRole('heading', { name: 'Offers' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeInTheDocument();
  });

  it('EmptyState without a title has no heading', () => {
    render(<EmptyState message="Nothing here" />);
    expect(screen.queryByRole('heading')).toBeNull();
  });

  it('ErrorState is an alert with a secondary Retry (never the brand primary)', async () => {
    const onRetry = vi.fn();
    const { container } = render(
      <ErrorState data-testid="err" message="Couldn't load your jobs" onRetry={onRetry} />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent("Couldn't load your jobs");
    const retry = screen.getByRole('button', { name: 'Retry' });
    expect(retry).toHaveAttribute('data-variant', 'secondary');
    await userEvent.click(retry);
    expect(onRetry).toHaveBeenCalledOnce();
    expect(await axeViolations(container)).toEqual([]);
  });

  it('ErrorState can be retrying or have no Retry', () => {
    const { rerender } = render(<ErrorState message="x" onRetry={() => {}} retrying />);
    expect(screen.getByRole('button', { name: 'Retry' })).toHaveAttribute('aria-busy', 'true');
    rerender(<ErrorState message="x" />);
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('SkeletonList announces loading once and hides the placeholders', async () => {
    const { container } = render(<SkeletonList label="Loading your jobs" count={2} />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading your jobs');
    expect(screen.getAllByTestId('skeleton')).toHaveLength(2);
    expect(screen.queryByRole('progressbar')).toBeNull(); // no spinner (design §6.2)
    expect(screen.queryByTestId('spinner')).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
  });

  it('Skeleton renders the requested number of lines', () => {
    const { container } = render(<Skeleton lines={5} />);
    expect(container.querySelectorAll('[data-testid="skeleton"] > span')).toHaveLength(5);
  });

  it('Banner is a polite status', () => {
    render(<Banner data-testid="offline" message="You're offline — showing your last update" />);
    expect(screen.getByRole('status')).toHaveTextContent(
      "You're offline — showing your last update",
    );
  });
});

describe('Toast', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('announces politely and hides itself after the duration', () => {
    const onHide = vi.fn();
    const { rerender } = render(<Toast message={null} onHide={onHide} />);
    expect(screen.queryByTestId('toast')).toBeNull();
    expect(screen.getByRole('status')).toBeInTheDocument(); // region mounted before the message
    rerender(<Toast message="This offer just expired — it's been reassigned" onHide={onHide} />);
    expect(screen.getByTestId('toast')).toHaveTextContent('This offer just expired');
    act(() => {
      vi.advanceTimersByTime(3999);
    });
    expect(onHide).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(onHide).toHaveBeenCalledOnce();
  });
});

describe('Sheet (dismissible, no modal trap)', () => {
  it('is a labeled dialog that takes focus and dismisses by Close, backdrop and Escape', async () => {
    const onDismiss = vi.fn();
    const { container, rerender } = render(
      <>
        <button>Decline</button>
        <Sheet open={false} title="Why decline?" onDismiss={onDismiss}>
          <p>Reason chips</p>
        </Sheet>
      </>,
    );
    expect(screen.queryByRole('dialog')).toBeNull();
    const opener = screen.getByRole('button', { name: 'Decline' });
    opener.focus();
    rerender(
      <>
        <button>Decline</button>
        <Sheet open title="Why decline?" onDismiss={onDismiss}>
          <p>Reason chips</p>
        </Sheet>
      </>,
    );
    const dialog = screen.getByRole('dialog', { name: 'Why decline?' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(document.activeElement).toBe(dialog);
    expect(await axeViolations(container)).toEqual([]);

    await userEvent.click(screen.getByText('Close'));
    fireEvent.click(screen.getByTestId('sheet-backdrop'));
    fireEvent.keyDown(document, { key: 'Escape' });
    fireEvent.keyDown(document, { key: 'Enter' });
    expect(onDismiss).toHaveBeenCalledTimes(3);

    rerender(
      <>
        <button>Decline</button>
        <Sheet open={false} title="Why decline?" onDismiss={onDismiss}>
          <p>Reason chips</p>
        </Sheet>
      </>,
    );
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Decline' }));
  });
});

describe('Sheet focus stability', () => {
  it('keeps focus in a field inside the sheet across parent re-renders', async () => {
    function Host() {
      const [note, setNote] = React.useState('');
      return (
        <Sheet open title="Why decline?" onDismiss={() => {}}>
          <label>
            Note
            <input value={note} onChange={(e) => setNote(e.target.value)} />
          </label>
        </Sheet>
      );
    }
    render(<Host />);
    const input = screen.getByLabelText('Note');
    await userEvent.click(input);
    await userEvent.type(input, 'far');
    expect(input).toHaveValue('far');
    expect(document.activeElement).toBe(input);
  });
});

describe('cx', () => {
  it('drops falsy parts', () => {
    expect(cx('a', false, null, undefined, 'b')).toBe('a b');
  });
});
