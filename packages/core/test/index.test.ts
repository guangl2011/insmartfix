import { describe, expect, it } from 'vitest';
import { CORE_PACKAGE } from '../src/index';

describe('@insmartfix/core scaffold', () => {
  it('exports its package marker', () => {
    expect(CORE_PACKAGE).toBe('@insmartfix/core');
  });
});
