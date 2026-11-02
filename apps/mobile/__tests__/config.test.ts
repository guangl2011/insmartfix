import { getMobileConfig } from '../src/config';

describe('getMobileConfig', () => {
  it('defaults to the contract mock', () => {
    expect(getMobileConfig({})).toEqual({
      dataSource: 'mock',
      apiBaseUrl: 'http://localhost:8000',
    });
  });

  it('reads EXPO_PUBLIC_* values', () => {
    expect(
      getMobileConfig({
        EXPO_PUBLIC_DATA_SOURCE: 'LIVE',
        EXPO_PUBLIC_API_BASE_URL: 'https://api.example.test/',
      }),
    ).toEqual({ dataSource: 'live', apiBaseUrl: 'https://api.example.test' });
  });
});
