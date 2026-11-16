#!/usr/bin/env node
// 直接校验 Markdown 源文件里的 LaTeX 公式能否被 KaTeX 渲染（不需要构建站点）。
//
// 用法：
//   node scripts/check/check_md_math.mjs <a.md> [b.md ...]
//   node scripts/check/check_md_math.mjs content/reinforcement_learning
//
// 检查项：
//   1. 每个 $...$ / $$...$$ 都能被 KaTeX 无错渲染；
//   2. 没有落单的 $（奇数个定界符）；
//   3. 围栏代码块（```）里的 $ 不计入，但会提示；
//   4. 报告残留的「代码样式公式」嫌疑（反引号里含 _{ ^ _ \ 等数学记号）。
//
// 退出码：0 = 通过；1 = 有问题。

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

const MATH_HINT = /[_^{}\\]|\b(argmax|argmin|sum|prod|frac|sqrt|mathbb|mathcal|epsilon|gamma|alpha|lambda|theta|pi|sigma|mu|max|min|log|exp)\b/;

function splitFences(text) {
  // 返回 [{code:boolean, text:string}]
  const parts = [];
  const lines = text.split('\n');
  let buf = [], inFence = false, fenceMark = '';
  for (const line of lines) {
    const m = line.match(/^\s*(`{3,}|~{3,})/);
    if (!inFence && m) {
      if (buf.length) { parts.push({ code: false, text: buf.join('\n') }); buf = []; }
      inFence = true; fenceMark = m[1];
      buf.push(line);
      continue;
    }
    if (inFence) {
      buf.push(line);
      if (m && m[1].startsWith(fenceMark[0]) && m[1].length >= fenceMark.length) {
        parts.push({ code: true, text: buf.join('\n') });
        buf = []; inFence = false; fenceMark = '';
      }
      continue;
    }
    buf.push(line);
  }
  if (buf.length) parts.push({ code: inFence, text: buf.join('\n') });
  return parts;
}

function extractMath(text) {
  // 先把行内代码 `...` 挖掉，它里面的 $ 不是公式定界符
  const holes = [];
  const masked = text.replace(/`[^`\n]*`/g, (m) => {
    holes.push(m);
    return `\u0001${holes.length - 1}\u0001`;
  });
  // 再取块级 $$...$$，最后取行内 $...$
  const found = [];
  let rest = masked;
  rest = rest.replace(/\$\$([\s\S]+?)\$\$/g, (_, tex) => {
    found.push({ tex, display: true });
    return '\u0000';
  });
  rest = rest.replace(/(?<!\\)\$([^$\n]+?)\$/g, (_, tex) => {
    found.push({ tex, display: false });
    return '\u0000';
  });
  return { found, rest };
}

function checkFile(file) {
  const raw = fs.readFileSync(file, 'utf8');
  const parts = splitFences(raw);
  const errors = [];
  let count = 0, stray = 0;
  const leftoverCode = [];

  for (const part of parts) {
    if (part.code) {
      if (part.text.includes('$')) {
        // 代码块里的 $ 合法，仅提示
      }
      continue;
    }
    const { found, rest } = extractMath(part.text);
    count += found.length;
    for (const { tex, display } of found) {
      try {
        katex.renderToString(tex, { displayMode: display, throwOnError: true });
      } catch (e) {
        errors.push({ tex, display, msg: e.message });
      }
    }
    const dollars = (rest.match(/\$/g) || []).length;
    if (dollars) stray += dollars;
    // 反引号里疑似公式
    const codes = part.text.match(/`[^`\n]+`/g) || [];
    for (const c of codes) {
      const inner = c.slice(1, -1);
      if (MATH_HINT.test(inner) && !/^[\w./-]+$/.test(inner)) leftoverCode.push(inner);
    }
  }

  return { file, count, errors, stray, leftoverCode };
}

function walk(dir) {
  const out = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...walk(p));
    else if (e.name.endsWith('.md') && e.name !== 'README.md') out.push(p);
  }
  return out;
}

const args = process.argv.slice(2);
if (!args.length) {
  console.error('用法: node scripts/check/check_md_math.mjs <md 文件或目录> [...]');
  process.exit(2);
}

let files = [];
for (const a of args) files.push(...(fs.statSync(a).isDirectory() ? walk(a) : [a]));

let totalMath = 0, totalErr = 0, totalStray = 0, totalLeftover = 0;
for (const f of files.sort()) {
  const r = checkFile(f);
  totalMath += r.count;
  totalErr += r.errors.length;
  totalStray += r.stray;
  totalLeftover += r.leftoverCode.length;
  if (r.errors.length || r.stray || r.leftoverCode.length) {
    console.log(`\n📄 ${f}`);
    console.log(`   公式 ${r.count}，失败 ${r.errors.length}，落单 $ ${r.stray}，疑似未转换 ${r.leftoverCode.length}`);
    for (const e of r.errors.slice(0, 8)) {
      console.log(`   ❌ ${e.display ? '[块]' : '[行]'} ${JSON.stringify(e.tex.slice(0, 120))}`);
      console.log(`      ${e.msg.slice(0, 160)}`);
    }
    for (const c of r.leftoverCode.slice(0, 8)) {
      console.log(`   ⚠️  仍是代码样式：\`${c.slice(0, 80)}\``);
    }
  }
}

console.log(`\n合计：${files.length} 个文件，${totalMath} 个公式，失败 ${totalErr}，落单 $ ${totalStray}，疑似未转换 ${totalLeftover}`);
process.exit(totalErr === 0 && totalStray === 0 && totalLeftover === 0 ? 0 : 1);