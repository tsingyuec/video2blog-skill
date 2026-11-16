#!/usr/bin/env node
// 检查博客的机械规范：时间戳数量与链接一致性、标题层级、图片写法。
//
// 用法：
//   node scripts/check/check_blog.mjs <博客文件或目录>
//
// 检查项：
//   1. 每个文件有且只有一个 H1，标题层级不跳级；
//   2. 【跳转到 MM:SS】链接里的 t 参数与显示时间一致，且每篇至少 10 个独立时间点；
//   3. 博客用标准 Markdown 图片，不写 <img> / width 属性。
//
// 内容正确性（是否覆盖、是否编造）不归脚本管，由内容审核抽检。
// 退出码：0 = 通过；1 = 有问题；2 = 用法错误。

import fs from 'node:fs';
import path from 'node:path';

const STAMP = /\[【跳转到\s*([0-9]{1,2}(?::[0-9]{2}){1,2})】\]\(([^)\s]+)\)/g;

function walk(dir) {
  const out = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) {
      if (e.name === 'transcripts' || e.name === 'assets') continue;
      out.push(...walk(p));
    } else if (e.name.endsWith('.md') && e.name !== 'README.md') {
      out.push(p);
    }
  }
  return out;
}

function seconds(label) {
  const parts = label.split(':').map(Number);
  return parts.reduce((acc, n) => acc * 60 + n, 0);
}

function checkFile(file) {
  const lines = fs.readFileSync(file, 'utf8').split('\n');
  const errors = [];
  let inFence = false, h1 = 0, prevLevel = 0;
  let stamps = 0;
  const unique = new Set();

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (/^\s*(`{3,}|~{3,})/.test(line)) { inFence = !inFence; continue; }
    if (inFence) continue;

    const heading = line.match(/^(#{1,6})\s+\S/);
    if (heading) {
      const level = heading[1].length;
      if (level === 1) h1++;
      if (prevLevel && level > prevLevel + 1) {
        errors.push({ line: i + 1, msg: `标题跳级：H${prevLevel} → H${level}` });
      }
      prevLevel = level;
    }

    if (/<img\b/i.test(line)) {
      errors.push({ line: i + 1, msg: '博客不要用 <img>，改用 ![图注](路径)' });
    }
    if (/!\[[^\]]*\]\([^)]*\)\{[^}]*width=/i.test(line) || /!\[[^\]]*\]\([^)]*\)\s*\{?width=/i.test(line)) {
      errors.push({ line: i + 1, msg: '图片不要写 width 属性' });
    }

    STAMP.lastIndex = 0;
    let m;
    while ((m = STAMP.exec(line))) {
      stamps++;
      const label = m[1];
      const url = m[2];
      const t = url.match(/[?&]t=(\d+)/);
      if (!t) {
        errors.push({ line: i + 1, msg: `时间戳链接缺 t 参数：${m[0]}` });
        continue;
      }
      const shown = seconds(label);
      const linked = Number(t[1]);
      if (shown !== linked) {
        errors.push({ line: i + 1, msg: `时间戳 ${label} 与 t=${linked} 不一致` });
      }
      unique.add(linked);
    }
  }

  if (h1 !== 1) errors.push({ line: 1, msg: `H1 数量为 ${h1}，应为 1` });
  if (unique.size < 10) errors.push({ line: 1, msg: `独立时间点仅 ${unique.size} 个，至少 10 个` });

  return { file, stamps, unique: unique.size, errors };
}

const args = process.argv.slice(2);
if (!args.length) {
  console.error('用法: node scripts/check/check_blog.mjs <博客文件或目录> [...]');
  process.exit(2);
}

let files = [];
for (const a of args) files.push(...(fs.statSync(a).isDirectory() ? walk(a) : [a]));

let bad = 0;
for (const f of files.sort()) {
  const r = checkFile(f);
  if (!r.errors.length) continue;
  bad++;
  console.log(`\n📄 ${f}`);
  console.log(`   时间戳 ${r.stamps} 个（独立 ${r.unique} 个），问题 ${r.errors.length} 处`);
  for (const e of r.errors.slice(0, 12)) console.log(`   ❌ L${e.line} ${e.msg}`);
}

console.log(`\n合计：${files.length} 个文件，${bad} 个有问题`);
process.exit(bad === 0 ? 0 : 1);
