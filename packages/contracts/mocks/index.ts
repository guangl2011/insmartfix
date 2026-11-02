/** `@insmartfix/contracts/mocks` — MSW contract mocks for `DATA_SOURCE=mock` (spec §4.2). */
export { createMockApi, mockToken, type MockApi, type MockApiOptions } from './handlers';
export {
  ASSET,
  CONTRACTOR,
  createMockDb,
  FAILURE_CODES,
  MOCK_REJECTED_PASSWORD,
  TENANT,
  uid,
  WO,
  type MockAsset,
  type MockDb,
  type MockUser,
  type MockWorkOrder,
} from './fixtures';
export {
  applyScenarioString,
  createScenarios,
  type RequestMatcher,
  type Scenarios,
} from './scenarios';
