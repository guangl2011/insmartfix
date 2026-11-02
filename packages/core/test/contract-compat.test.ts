import { describe, expectTypeOf, it } from 'vitest';
import type * as Contract from '@insmartfix/contracts';
import type { CompletionReport, FailureCode, PartUsed } from '../src';

// Core keeps structural copies of the wire shapes so it has no runtime dependency on the
// generated client; these checks fail typecheck if the contract drifts from them.
describe('core wire types match @insmartfix/contracts', () => {
  it('FailureCode', () => {
    expectTypeOf<Contract.FailureCode>().toEqualTypeOf<FailureCode>();
  });

  it('CompletionReport and PartUsed', () => {
    expectTypeOf<CompletionReport>().toExtend<Contract.CompletionReport>();
    expectTypeOf<PartUsed>().toEqualTypeOf<Contract.components['schemas']['PartUsed']>();
    expectTypeOf<Required<Contract.CompletionReport>>().toExtend<CompletionReport>();
  });
});
