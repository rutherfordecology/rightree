// Resolve species names to NZTCS taxa with Occurd's but-is-it-threatened
// resolver (nine passes: corrections, exact, variants, prefix, nominate,
// subsequence, one-letter typo, Latin gender, parent species).
//
// Each name is tried as given and as NZOR's accepted name (synonym step).
//
// Usage: node scripts/resolve_names.mjs <names.json> <out.json>
//   names.json: ["Zealandia pustulata", ...]
//   out.json:   {"Zealandia pustulata": {"n": "...", "via": "...", "tried": "..."} | null}
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const bit = path.resolve(here, '..', '..', 'Occurd', 'but-is-it-threatened');
const read = f => JSON.parse(fs.readFileSync(path.join(bit, f), 'utf8'));

const ctx = { window: {}, console };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(bit, 'nztcs-resolver.js'), 'utf8'), ctx);
const resolver = ctx.window.NztcsResolver.build(read('nztcs_slim.json'), read('name_corrections.json'));
const nzor = read('nzor_names_v2.json');

const [inPath, outPath] = process.argv.slice(2);
const names = JSON.parse(fs.readFileSync(inPath, 'utf8'));
const out = {};
for (const name of names) {
  const rec = nzor[name.toLowerCase()];
  const acc = rec && rec.acc;
  let hit = null;
  for (const tried of acc ? [acc, name] : [name]) {
    const r = resolver.resolve(tried);
    if (r) { hit = { n: r.n, via: (tried === name ? '' : 'nzor synonym, ') + r.via, tried }; break; }
  }
  out[name] = hit;
}
fs.writeFileSync(outPath, JSON.stringify(out, null, 1));
console.log(`resolved ${Object.values(out).filter(Boolean).length} of ${names.length}`);
