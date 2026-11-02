// insmartfix/no-status-color (M3-T4; NFR-4, FR-2.3; the lint half of T-THEME-1 and T-INBOX-2).
// Reserved status color may appear only in HealthScore and RiskBadge. Outside them it reports:
//   - importing `@insmartfix/tokens/status` (static, dynamic, require, re-export);
//   - importing a `status*` binding from `@insmartfix/tokens`;
//   - status hex / rgb() literals and `--status-*` / `--crit-bright` variables in strings,
//     template literals and JSX text.
import { ALLOWED_COMPONENTS, STATUS_MODULE, findStatusColor, isAllowedFile } from './patterns.mjs';

const TOKENS_MAIN = '@insmartfix/tokens';

/** @type {import('eslint').Rule.RuleModule} */
const rule = {
  meta: {
    type: 'problem',
    docs: {
      description:
        'Reserve the status (health/risk) color scale for the HealthScore and RiskBadge components (NFR-4).',
    },
    schema: [
      {
        type: 'object',
        properties: { allow: { type: 'array', items: { type: 'string' }, uniqueItems: true } },
        additionalProperties: false,
      },
    ],
    messages: {
      statusImport:
        "'{{source}}' is reserved for HealthScore/RiskBadge (NFR-4). Use a neutral or brand token role instead.",
      statusBinding:
        "'{{name}}' from '@insmartfix/tokens' is status color, reserved for HealthScore/RiskBadge (NFR-4).",
      statusColor:
        "Status color '{{match}}' is reserved for HealthScore/RiskBadge (NFR-4). Use a token role instead.",
    },
  },
  create(context) {
    const allow = context.options[0]?.allow ?? ALLOWED_COMPONENTS;
    if (isAllowedFile(context.filename, allow)) return {};

    const checkSource = (node, source) => {
      if (typeof source === 'string' && STATUS_MODULE.test(source))
        context.report({ node, messageId: 'statusImport', data: { source } });
    };
    const checkText = (node, text) => {
      const hit = findStatusColor(text);
      if (hit) context.report({ node, messageId: 'statusColor', data: { match: hit.match } });
    };

    return {
      ImportDeclaration(node) {
        checkSource(node.source, node.source.value);
        if (node.source.value !== TOKENS_MAIN) return;
        for (const s of node.specifiers) {
          const name =
            s.type === 'ImportSpecifier'
              ? s.imported.type === 'Identifier'
                ? s.imported.name
                : s.imported.value
              : null;
          if (name && /^status/i.test(name))
            context.report({ node: s, messageId: 'statusBinding', data: { name } });
        }
      },
      ExportNamedDeclaration(node) {
        if (node.source) checkSource(node.source, node.source.value);
      },
      ExportAllDeclaration(node) {
        checkSource(node.source, node.source.value);
      },
      ImportExpression(node) {
        if (node.source.type === 'Literal') checkSource(node.source, node.source.value);
      },
      CallExpression(node) {
        const [arg] = node.arguments;
        const isRequire =
          (node.callee.type === 'Identifier' && node.callee.name === 'require') ||
          (node.callee.type === 'MemberExpression' &&
            node.callee.object.type === 'Identifier' &&
            node.callee.object.name === 'require');
        if (isRequire && arg?.type === 'Literal') checkSource(arg, arg.value);
      },
      Literal(node) {
        if (typeof node.value === 'string' && !isModuleSource(node)) checkText(node, node.value);
      },
      TemplateElement(node) {
        checkText(node, node.value.raw);
      },
      JSXText(node) {
        checkText(node, node.value);
      },
    };
  },
};

/** Module specifiers are handled by checkSource; don't double-report them as color literals. */
function isModuleSource(node) {
  const p = node.parent;
  return (
    !!p &&
    (p.type === 'ImportDeclaration' ||
      p.type === 'ExportNamedDeclaration' ||
      p.type === 'ExportAllDeclaration' ||
      p.type === 'ImportExpression') &&
    p.source === node
  );
}

export default rule;
