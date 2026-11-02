/** AppState → core VisibilityPort: visible only while `active` (plan §4). */
import { AppState, type AppStateStatus } from 'react-native';
import type { VisibilityPort } from '@insmartfix/core';

export function createAppStateVisibility(
  appState: Pick<typeof AppState, 'currentState' | 'addEventListener'> = AppState,
): VisibilityPort {
  let visible = appState.currentState === 'active' || appState.currentState == null;
  const listeners = new Set<(visible: boolean) => void>();
  appState.addEventListener('change', (s: AppStateStatus) => {
    // `inactive` (iOS app switcher, incoming call) is not background: keep timers until it settles.
    if (s === 'inactive') return;
    const next = s === 'active';
    if (next === visible) return;
    visible = next;
    for (const l of [...listeners]) l(next);
  });
  return {
    isVisible: () => visible,
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}
