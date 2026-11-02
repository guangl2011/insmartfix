import { getServerConfig } from './config';

describe('getServerConfig', () => {
  it('defaults to live against localhost', () => {
    expect(getServerConfig({} as NodeJS.ProcessEnv)).toEqual({
      dataSource: 'live',
      apiBaseUrl: 'http://localhost:8000',
    });
  });

  it('reads DATA_SOURCE and API_BASE_URL (trailing slash trimmed)', () => {
    const env = {
      DATA_SOURCE: ' MOCK ',
      API_BASE_URL: 'http://api:8000/',
    } as unknown as NodeJS.ProcessEnv;
    expect(getServerConfig(env)).toEqual({ dataSource: 'mock', apiBaseUrl: 'http://api:8000' });
  });

  it('rejects an unknown DATA_SOURCE', () => {
    expect(() => getServerConfig({ DATA_SOURCE: 'prod' } as unknown as NodeJS.ProcessEnv)).toThrow(
      /DATA_SOURCE/,
    );
  });
});
