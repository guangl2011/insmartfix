/**
 * @insmartfix/core — pure, platform-free logic shared by apps/web and apps/mobile (plan §4).
 * Test adapters: `@insmartfix/core/testing`.
 */
export const CORE_PACKAGE = '@insmartfix/core' as const;

export * from './ports';
export * from './drafts';
export * from './sla';
export * from './ordering';
export * from './completion';
export * from './queue';
export * from './inbox';
