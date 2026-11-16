// 定位并加载 KaTeX：检查脚本不绑定具体项目，优先用 KATEX_PATH，
// 否则从当前目录向上找 vendor/katex/katex.mjs 或 node_modules/katex/dist/katex.mjs。
//
// 用法（一般不需要直接跑）：
//   KATEX_PATH=/path/to/vendor/katex/katex.mjs node scripts/check/check_md_math.mjs <md...>

import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

function resolveKatex(value) {
  if (!value) return null;
  const p = path.resolve(value);
  if (fs.existsSync(p) && fs.statSync(p).isFile()) return p;
  const nested = path.join(p, 'katex.mjs');
  return fs.existsSync(nested) ? nested : null;
}

export async function loadKatex() {
  const candidates = [resolveKatex(process.env.KATEX_PATH)];
  let dir = process.cwd();
  for (let i = 0; i < 6; i++) {
    candidates.push(
      path.join(dir, 'vendor', 'katex', 'katex.mjs'),
      path.join(dir, 'node_modules', 'katex', 'dist', 'katex.mjs'),
    );
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  for (const file of candidates.filter(Boolean)) {
    if (fs.existsSync(file)) {
      const mod = await import(pathToFileURL(file).href);
      return mod.default ?? mod;
    }
  }
  throw new Error(
    '找不到 KaTeX。请在项目根目录运行（需有 vendor/katex/katex.mjs），' +
    '或设置 KATEX_PATH=/path/to/katex.mjs。'
  );
}
