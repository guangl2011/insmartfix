import { writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { renderCss } from '../src/index';

const out = fileURLToPath(new URL('../tokens.css', import.meta.url));
writeFileSync(out, renderCss());
console.log(`wrote ${out}`);
