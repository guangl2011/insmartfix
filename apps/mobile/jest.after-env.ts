// Fresh keychain and AsyncStorage for every test (no state leaks between cases).
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';

afterEach(async () => {
  (SecureStore as unknown as { __store: Map<string, string> }).__store.clear();
  await AsyncStorage.clear();
});
