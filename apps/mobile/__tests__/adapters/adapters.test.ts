import type { AppStateStatus } from 'react-native';
import {
  createAppStateVisibility,
  createAsyncStorage,
  createNetInfoConnectivity,
  isOnlineState,
} from '../../src/adapters';

describe('core port adapters (M5-T2)', () => {
  it('NetInfo → ConnectivityPort: offline when disconnected or unreachable, notifies on change', async () => {
    let emit: (s: {
      isConnected: boolean | null;
      isInternetReachable: boolean | null;
    }) => void = () => {};
    const netInfo = {
      addEventListener: (l: typeof emit) => {
        emit = l;
        return () => {};
      },
      fetch: () => Promise.resolve({ isConnected: true, isInternetReachable: null }),
    };
    const port = createNetInfoConnectivity(netInfo as never);
    await Promise.resolve();
    expect(port.isOnline()).toBe(true);
    const seen: boolean[] = [];
    const off = port.subscribe((o) => seen.push(o));
    emit({ isConnected: false, isInternetReachable: false });
    emit({ isConnected: false, isInternetReachable: false });
    emit({ isConnected: true, isInternetReachable: true });
    off();
    emit({ isConnected: true, isInternetReachable: false });
    expect(seen).toEqual([false, true]);
    expect(port.isOnline()).toBe(false);
    expect(isOnlineState({ isConnected: true, isInternetReachable: null })).toBe(true);
  });

  it('AppState → VisibilityPort: active is visible, background hides, inactive is ignored', () => {
    let emit: (s: AppStateStatus) => void = () => {};
    const appState = {
      currentState: 'active' as AppStateStatus,
      addEventListener: (_: string, l: typeof emit) => {
        emit = l;
        return { remove: () => {} };
      },
    };
    const port = createAppStateVisibility(appState as never);
    const seen: boolean[] = [];
    port.subscribe((v) => seen.push(v));
    emit('inactive');
    emit('background');
    emit('background');
    emit('active');
    expect(seen).toEqual([false, true]);
    expect(port.isVisible()).toBe(true);
  });

  it('AsyncStorage → StoragePort with prefix listing', async () => {
    const s = createAsyncStorage();
    await s.set('draft:u:1', 'a');
    await s.set('queue:u', 'b');
    expect(await s.get('draft:u:1')).toBe('a');
    expect(await s.keys('draft:')).toEqual(['draft:u:1']);
    expect((await s.keys()).sort()).toEqual(['draft:u:1', 'queue:u']);
    await s.delete('draft:u:1');
    expect(await s.get('draft:u:1')).toBeNull();
  });
});
