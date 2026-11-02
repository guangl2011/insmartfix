// ESLint plugin `insmartfix`, used by the root eslint.config.mjs for every workspace
// (apps/web, apps/mobile, packages/ui-web, packages/core, packages/contracts).
import noStatusColor from './no-status-color.mjs';

const plugin = {
  meta: { name: 'eslint-plugin-insmartfix' },
  rules: { 'no-status-color': noStatusColor },
};

export default plugin;
