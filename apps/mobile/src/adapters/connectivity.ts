/** NetInfo → core ConnectivityPort (plan §4: mobile supplies NetInfo). */
import NetInfo, { type NetInfoState } from '@react-native-community/netinfo';
import type { ConnectivityPort } from '@insmartfix/core';

/** Online unless NetInfo says the device is disconnected or the internet is unreachable. */
export function isOnlineState(
  s: Pick<NetInfoState, 'isConnected' | 'isInternetReachable'>,
): boolean {
  return s.isConnected !== false && s.isInternetReachable !== false;
}

export function createNetInfoConnectivity(
  netInfo: Pick<typeof NetInfo, 'addEventListener' | 'fetch'> = NetInfo,
): ConnectivityPort {
  // Optimistic until the first NetInfo report: a request is the real probe (and fails fast).
  let online = true;
  const listeners = new Set<(online: boolean) => void>();
  const update = (s: NetInfoState) => {
    const next = isOnlineState(s);
    if (next === online) return;
    online = next;
    for (const l of [...listeners]) l(next);
  };
  netInfo.addEventListener(update);
  netInfo.fetch().then(update, () => {});
  return {
    isOnline: () => online,
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}
