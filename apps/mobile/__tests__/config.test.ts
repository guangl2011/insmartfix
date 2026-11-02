import { getMobileConfig } from '../src/config';

describe('getMobileConfig', () => {
  it('defaults to the contract mock', () => {
    expect(getMobileConfig({})).toEqual({
      dataSource: 'mock',
      apiBaseUrl: 'http://localhost:8000',
      sentryDsn: null,
      mockScenarios: '',
    });
  });

  it('reads EXPO_PUBLIC_* values', () => {
    expect(
      getMobileConfig({
        EXPO_PUBLIC_DATA_SOURCE: 'LIVE',
        EXPO_PUBLIC_API_BASE_URL: 'https://api.example.test/',
      }),
    ).toEqual({
      dataSource: 'live',
      apiBaseUrl: 'https://api.example.test',
      sentryDsn: null,
      mockScenarios: '',
    });
  });

  it('reads the optional crash-reporting DSN and mock scenarios', () => {
    expect(
      getMobileConfig({
        EXPO_PUBLIC_SENTRY_DSN: ' https://k@o.example/1 ',
        EXPO_PUBLIC_MOCK_SCENARIOS: 'race',
      }),
    ).toMatchObject({ sentryDsn: 'https://k@o.example/1', mockScenarios: 'race' });
  });
});

describe('app.json platform floor (NFR-8)', () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const app = require('../app.json') as {
    expo: { plugins: unknown[]; userInterfaceStyle: string };
  };
  const props = app.expo.plugins.find(
    (p): p is [string, { ios: { deploymentTarget: string }; android: { minSdkVersion: number } }] =>
      Array.isArray(p) && p[0] === 'expo-build-properties',
  );

  // Expo SDK 58 refuses a deployment target below iOS 16.4 (the lowest iOS 16 it can build).
  it('targets iOS 16 (16.4, the SDK floor) and Android 10+ (API 29)', () => {
    expect(props?.[1].ios.deploymentTarget).toBe('16.4');
    expect(props?.[1].android.minSdkVersion).toBe(29);
  });

  it('follows the system light/dark setting (NFR-9)', () => {
    expect(app.expo.userInterfaceStyle).toBe('automatic');
  });
});

describe('app.json platform floor (NFR-8)', () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const app = require('../app.json') as {
    expo: { plugins: unknown[]; userInterfaceStyle: string };
  };
  const props = app.expo.plugins.find(
    (p): p is [string, { ios: { deploymentTarget: string }; android: { minSdkVersion: number } }] =>
      Array.isArray(p) && p[0] === 'expo-build-properties',
  );

  // Expo SDK 58 refuses a deployment target below iOS 16.4 (the lowest iOS 16 it can build).
  it('targets iOS 16 (16.4, the SDK floor) and Android 10+ (API 29)', () => {
    expect(props?.[1].ios.deploymentTarget).toBe('16.4');
    expect(props?.[1].android.minSdkVersion).toBe(29);
  });

  it('follows the system light/dark setting (NFR-9)', () => {
    expect(app.expo.userInterfaceStyle).toBe('automatic');
  });
});
