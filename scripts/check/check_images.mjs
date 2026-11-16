#!/usr/bin/env node
// 校验 Markdown 里的图片引用：文件在不在、格式对不对、有没有「存着但没人用」的图。
//
// 用法：
//   node scripts/check/check_images.mjs content/K8s集群
//   node scripts/check/check_images.mjs content/x/blog/某篇.md
//   node scripts/check/check_images.mjs content --quiet      # 只打合计
//   node scripts/check/check_images.mjs content --list-orphans   # 只输出孤儿图路径，便于 xargs rm
//
// 检查项（前四项算问题，会让退出码变 1；后两项只是提醒）：
//   1. 引用的图片按 unquote 后的相对路径能在磁盘上找到（兼容 `%29`/`%20` 编码与 `<...>` 写法）；
//   2. 是普通文件、不是 0 字节；
//   3. 扩展名与实际文件头一致（`.png` 其实是 JPEG / `.webp` 其实是 PNG 这类会报出来）；
//   4. 扩展名在站点发布白名单内（不在的话 build_site.py 会静默丢掉，线上就是 404）。
//   5. ⚠️ 未被任何文章引用（孤儿图，可删除或挪到别处）；
//   6. ⚠️ 上不了站（见第 4 项）。
//
// 解析规则与 site/build_site.py 保持一致：目标允许一层成对括号、允许 <...> 包裹；
// 跳过外部链接；围栏代码块与行内代码整段挖空（保留行号）。另外也认 `<img src="...">`。
//
// 孤儿图只在传入目录时扫描（扫这些目录下所有 .md 的引用做对照）。
// 只传单个 .md 文件时不做孤儿检查。
//
// 退出码：0 = 通过；1 = 有缺失/空文件/格式不符；2 = 用法错误。

import fs from 'node:fs';
import path from 'node:path';

// 与 site/build_site.py 的 ASSET_EXTS 保持一致：不在表里的扩展名不会上站
const ASSET_EXTS = new Set([
  '.webp', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.avif', '.bmp', '.ico', '.pdf',
]);
// 孤儿检查只看图片（pdf 可能是正文附件，不按「配图」算）
const IMAGE_EXTS = new Set([...ASSET_EXTS].filter((e) => e !== '.pdf'));

// 允许的「扩展名 -> 文件头」对应关系（.jpg/.jpeg 同属 JPEG）
const EXT_FORMAT = {
  '.png': 'png', '.jpg': 'jpeg', '.jpeg': 'jpeg', '.gif': 'gif', '.webp': 'webp',
  '.avif': 'avif', '.bmp': 'bmp', '.ico': 'ico', '.svg': 'svg',
};

// 图片引用：![alt](目标 "title")，目标可为 <...> 或最多含一层成对括号
const IMG_RE = /!\[[^\]]*\]\(\s*(<[^>]*>|(?:[^()\n]|\([^()\n]*\))*?)(?:\s+"[^"]*")?\s*\)/g;
// HTML 写法：<img src="...">（少数文章用 HTML 表格并排贴图）
const IMG_TAG_RE = /<img\b[^>]*?\bsrc\s*=\s*["']([^"']+)["']/gi;

const isExternal = (t) =>
  !t || t.startsWith('#') || t.startsWith('//') || t.startsWith('/') ||
  /^[a-zA-Z][a-zA-Z0-9+.\-]*:/.test(t);

/** 把围栏代码块整段挖空、行内代码挖掉，保留行数（行号不变）。 */
function maskCode(text) {
  const lines = text.split('\n');
  let inFence = false, mark = '';
  return lines.map((line) => {
    const m = line.match(/^\s*(`{3,}|~{3,})/);
    if (!inFence && m) { inFence = true; mark = m[1]; return ''; }
    if (inFence) {
      if (m && m[1][0] === mark[0] && m[1].length >= mark.length) inFence = false;
      return '';
    }
    return line.replace(/`[^`\n]*`/g, '');
  });
}

/** 目标 -> 候选相对路径（先按 # 切锚点，再把整串当路径试；带百分号编码的先解码）。 */
function candidates(target) {
  const out = [];
  const specs = [];
  const hash = target.indexOf('#');
  if (hash >= 0) {
    specs.push(target.slice(0, hash), target);
  } else {
    specs.push(target);
  }
  for (const p of specs) {
    let decoded = p;
    try { decoded = decodeURIComponent(p); } catch { /* 非法编码就按原样用 */ }
    const norm = path.posix.normalize(decoded.replace(/\\/g, '/'));
    if (!out.includes(norm)) out.push(norm);
  }
  return out;
}

/** 读文件头判断真实格式。 */
function sniff(file) {
  const fd = fs.openSync(file, 'r');
  try {
    const buf = Buffer.alloc(512);
    const n = fs.readSync(fd, buf, 0, buf.length, 0);
    const b = buf.subarray(0, n);
    const asc = (from, to) => b.toString('latin1', from, to);
    if (b.length >= 8 && b.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))) return 'png';
    if (b.length >= 3 && b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff) return 'jpeg';
    if (b.length >= 6 && (asc(0, 6) === 'GIF87a' || asc(0, 6) === 'GIF89a')) return 'gif';
    if (b.length >= 12 && asc(0, 4) === 'RIFF' && asc(8, 12) === 'WEBP') return 'webp';
    if (b.length >= 12 && asc(4, 8) === 'ftyp' && ['avif', 'avis'].includes(asc(8, 12))) return 'avif';
    if (b.length >= 2 && b[0] === 0x42 && b[1] === 0x4d) return 'bmp';
    if (b.length >= 4 && b[0] === 0 && b[1] === 0 && b[2] === 1 && b[3] === 0) return 'ico';
    if (asc(0, 4) === '%PDF') return 'pdf';
    // SVG 是文本，可能带 BOM / XML 声明 / 注释 / DOCTYPE
    if (/^\uFEFF?\s*(<\?xml[\s\S]*?\?>\s*)?(<!--[\s\S]*?-->\s*)*(<!DOCTYPE[\s\S]*?>\s*)?<svg/i.test(b.toString('utf8'))) return 'svg';
    return 'unknown';
  } finally {
    fs.closeSync(fd);
  }
}

function walk(dir, out = { md: [], img: [] }) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) { walk(p, out); continue; }
    const ext = path.extname(e.name).toLowerCase();
    if (ext === '.md') out.md.push(p);
    else if (IMAGE_EXTS.has(ext)) out.img.push(p);
  }
  return out;
}

const args = process.argv.slice(2);
const quiet = args.includes('--quiet') || args.includes('--list-orphans');
const listOrphans = args.includes('--list-orphans');
const inputs = args.filter((a) => !a.startsWith('--'));
if (!inputs.length) {
  console.error('用法: node scripts/check/check_images.mjs <md 文件或目录> [...] [--quiet]');
  process.exit(2);
}

const found = { md: [], img: [] };
let scanOrphans = false;
for (const a of inputs) {
  if (fs.statSync(a).isDirectory()) {
    scanOrphans = true;
    walk(a, found);
  } else {
    found.md.push(a);
  }
}
const files = [...new Set(found.md)].sort();

// 同一个图片可能被多篇文章引用：只检查一次，报告时只留首个引用位置
const seen = new Map(); // 绝对路径 -> 首个引用
const problems = new Map(); // 绝对路径 -> { kind, detail, ref }
let refCount = 0;

for (const md of files) {
  const lines = maskCode(fs.readFileSync(md, 'utf8'));
  const dir = path.dirname(md);

  lines.forEach((line, i) => {
    const targets = [];
    for (const m of line.matchAll(IMG_RE)) targets.push(m[1]);
    for (const m of line.matchAll(IMG_TAG_RE)) targets.push(m[1]);

    for (let target of targets) {
      target = target.trim();
      if (target.startsWith('<') && target.endsWith('>')) target = target.slice(1, -1).trim();
      if (isExternal(target)) continue;
      refCount += 1;

      let resolved = null;
      const tried = [];
      for (const cand of candidates(target)) {
        for (const p of [path.resolve(dir, cand), path.resolve(cand)]) {
          tried.push(p);
          if (fs.existsSync(p)) { resolved = p; break; }
        }
        if (resolved) break;
      }

      const ref = `${md}:${i + 1}`;
      if (!resolved) {
        if (!problems.has(tried[0])) problems.set(tried[0], { kind: 'missing', detail: `目标 ${target}`, ref });
        continue;
      }
      if (seen.has(resolved)) continue;
      seen.set(resolved, ref);

      const st = fs.statSync(resolved);
      if (!st.isFile()) {
        problems.set(resolved, { kind: 'notfile', detail: '目标是目录，不是文件', ref });
        continue;
      }
      if (st.size === 0) {
        problems.set(resolved, { kind: 'empty', detail: '文件为 0 字节', ref });
        continue;
      }
      const ext = path.extname(resolved).toLowerCase();
      if (!ASSET_EXTS.has(ext)) {
        problems.set(resolved, { kind: 'unpublished', detail: `扩展名 ${ext || '(无)'} 不在发布白名单，构建后不会上站`, ref });
        continue;
      }
      if (!EXT_FORMAT[ext]) continue; // .pdf 等不做格式比对
      const real = sniff(resolved);
      if (real !== EXT_FORMAT[ext]) {
        problems.set(resolved, {
          kind: 'format',
          detail: `扩展名 ${ext}，实际是 ${real === 'unknown' ? '无法识别的格式' : real.toUpperCase()}`,
          ref,
        });
      }
    }
  });
}

// 孤儿图：目录里存在、但没有任何被扫描的 .md 引用
const orphans = scanOrphans
  ? found.img.filter((p) => !seen.has(path.resolve(p))).sort()
  : [];
const orphanBytes = orphans.reduce((s, p) => s + fs.statSync(p).size, 0);
const mb = (n) => `${(n / 1024 / 1024).toFixed(1)} MB`;

const order = ['missing', 'notfile', 'empty', 'format', 'unpublished'];
const label = {
  missing: '❌ 文件不存在',
  notfile: '❌ 不是文件（是个目录）',
  empty: '❌ 0 字节',
  format: '❌ 格式与扩展名不符',
  unpublished: '⚠️  不会上站（扩展名不在发布白名单）',
};

if (!quiet) {
  for (const kind of order) {
    const items = [...problems.entries()].filter(([, v]) => v.kind === kind);
    if (!items.length) continue;
    console.log(`\n${label[kind]}（${items.length}）`);
    for (const [file, v] of items.slice(0, 30)) {
      console.log(`   ${v.ref}`);
      console.log(`      ${path.relative(process.cwd(), file)}`);
      console.log(`      ${v.detail}`);
    }
    if (items.length > 30) console.log(`   …另有 ${items.length - 30} 条`);
  }
  if (orphans.length) {
    console.log(`\n⚠️  存在但没被任何文章引用（${orphans.length} 个，共 ${mb(orphanBytes)}；可删除或挪到别处）`);
    for (const p of orphans.slice(0, 30)) {
      console.log(`   ${path.relative(process.cwd(), p)}  (${Math.round(fs.statSync(p).size / 1024)} KB)`);
    }
    if (orphans.length > 30) console.log(`   …另有 ${orphans.length - 30} 条`);
  }
}

const count = (kind) => [...problems.values()].filter((v) => v.kind === kind).length;

if (listOrphans) {
  for (const p of orphans) console.log(p);
  process.exit(0);
}
console.log(
  `\n合计：${files.length} 个 .md，图片引用 ${refCount} 处` +
    `，缺失 ${count('missing')}，非文件 ${count('notfile')}，空文件 ${count('empty')}` +
    `，格式不符 ${count('format')}` +
    `，未发布 ${count('unpublished')}` +
    (scanOrphans ? `，未被引用 ${orphans.length}（${mb(orphanBytes)}）` : ''),
);

const hard = count('missing') + count('notfile') + count('empty') + count('format');
process.exit(hard === 0 ? 0 : 1);
