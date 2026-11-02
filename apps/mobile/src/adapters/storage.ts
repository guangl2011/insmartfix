/**
 * AsyncStorage → core StoragePort (drafts, offline queue, cached inbox/packets). Durable across
 * app kill. Never used for the auth token: that lives only in expo-secure-store (FR-1.3).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import type { StoragePort } from '@insmartfix/core';

type AsyncStorageLike = Pick<
  typeof AsyncStorage,
  'getItem' | 'setItem' | 'removeItem' | 'getAllKeys'
>;

export function createAsyncStorage(store: AsyncStorageLike = AsyncStorage): StoragePort {
  return {
    get: (key) => store.getItem(key),
    set: (key, value) => store.setItem(key, value),
    delete: (key) => store.removeItem(key),
    keys: async (prefix = '') => (await store.getAllKeys()).filter((k) => k.startsWith(prefix)),
  };
}
