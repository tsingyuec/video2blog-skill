#!/usr/bin/env node
// 校验构建产物里的 KaTeX 公式能否被真正渲染（而不是靠肉眼猜）。
//
// 用法：
//   node scripts/check/check_katex.mjs build/site/<页面>.html
//   node scripts/check/check_katex.mjs build/site/reinforcement_learning --recursive
//
// 退出码：0 = 全部可渲染；1 = 有公式报错或页面里还有未转换的 $...$。

import fs from 'node:fs';
import path from 'node:path';
import { loadKatex } from './katex.mjs';

let katex;
try {
  katex = await loadKatex();
} catch (e) {
  console.error(e.message);
  process.exit(2);
}

const INLINE = /<span class="arithmatex">\\\(([\s\S]*?)\\\)<\/span>/g;
const DISPLAY = /<div class="arithmatex">\\\[([\s\S]*?)\\\]<\/div>/g;

function decodeEntities(s) {
  return s.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"')
          .replace(/&#39;/g, "'").replace(/&amp;/g, '&');
}

function articleBody(html) {
  const m = html.match(/<article[^>]*>([\s\S]*?)<\/article>/);
  return m ? m[1] : html;
}

function collect(body) {
  const out = [];
  for (const [re, display] of [[INLINE, false], [DISPLAY, true]]) {
    re.lastIndex = 0;
    let m;
    while ((m = re.exec(body))) out.push({ tex: decodeEntities(m[1]), display });
  }
  return out;
}

function checkFile(file) {
  const body = articleBody(fs.readFileSync(file, 'utf8'));
  const items = collect(body);
  const errors = [];
  for (const { tex, display } of items) {
    try {
      katex.renderToString(tex, { displayMode: display, throwOnError: true });
    } catch (e) {
      errors.push({ tex, display, msg: e.message });
    }
  }
  // 正文里残留的裸 $（排除 code/pre 内的合法美元符号）
  let stripped = body
    .replace(/<pre[\s\S]*?<\/pre>/g, '')
    .replace(/<code[\s\S]*?<\/code>/g, '')
    .replace(/<span class="arithmatex">[\s\S]*?<\/span>/g, '')
    .replace(/<div class="arithmatex">[\s\S]*?<\/div>/g, '')
    .replace(/<[^>]+>/g, '');
  const strayDollar = (stripped.match(/\$/g) || []).length;
  return { file, count: items.length, errors, strayDollar };
}

function walk(dir) {
  const out = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...walk(p));
    else if (e.name.endsWith('.html') && e.name !== 'README.html') out.push(p);
  }
  return out;
}

const target = process.argv[2];
if (!target) {
  console.error('用法: node scripts/check/check_katex.mjs <html 文件或目录> [--recursive]');
  process.exit(2);
}

const files = fs.statSync(target).isDirectory() ? walk(target) : [target];
let total = 0, bad = 0, pages = 0, pagesWithStray = 0;

for (const f of files.sort()) {
  const r = checkFile(f);
  if (r.count === 0 && r.strayDollar === 0) continue;
  pages++;
  total += r.count;
  if (r.errors.length || r.strayDollar) {
    bad += r.errors.length;
    if (r.strayDollar) pagesWithStray++;
    console.log(`\n📄 ${f}`);
    console.log(`   公式 ${r.count} 个，失败 ${r.errors.length} 个，残留 $ ${r.strayDollar} 处`);
    for (const e of r.errors.slice(0, 10)) {
      console.log(`   ❌ ${e.display ? '[块]' : '[行]'} ${JSON.stringify(e.tex.slice(0, 120))}`);
      console.log(`      ${e.msg.slice(0, 160)}`);
    }
  }
}

console.log(`\n合计：${pages} 个页面，${total} 个公式，失败 ${bad} 个，含残留 $ 的页面 ${pagesWithStray} 个`);
process.exit(bad === 0 && pagesWithStray === 0 ? 0 : 1);