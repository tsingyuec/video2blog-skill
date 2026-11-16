#!/usr/bin/env python3
"""检查博客的机械规范：时间戳数量与链接一致性、标题层级、图片写法。

用法：
    python3 scripts/check/check_blog.py <博客文件或目录>

检查项：
  1. 每个文件有且只有一个 H1，标题层级不跳级；
  2. 【跳转到 MM:SS】链接里的 t 参数与显示时间一致，且每篇至少 10 个独立时间点；
  3. 博客用标准 Markdown 图片，不写 <img> / width 属性。

内容正确性（是否覆盖、是否编造）不归脚本管，由内容审核抽检。
退出码：0 = 通过；1 = 有问题；2 = 用法错误。
"""

import argparse
import os
import re
import sys
from pathlib import Path

STAMP = re.compile(r'\[【跳转到\s*([0-9]{1,2}(?::[0-9]{2}){1,2})】\]\(([^)\s]+)\)')
WIDTH_RE = re.compile(r'!\[[^\]]*\]\([^)]*\)\s*\{?width=', re.I)


def walk(root: Path) -> list[Path]:
    out = []
    for current, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in {"transcripts", "assets"})
        for name in sorted(names):
            if name.endswith(".md") and name != "README.md":
                out.append(Path(current) / name)
    return out


def seconds(label: str) -> int:
    n = 0
    for part in label.split(":"):
        n = n * 60 + int(part)
    return n


def check_file(file: Path) -> dict:
    lines = file.read_text(encoding="utf-8").split("\n")
    errors = []
    in_fence = False
    h1 = 0
    prev_level = 0
    stamps = 0
    unique = set()

    for i, line in enumerate(lines, 1):
        if re.match(r'^\s*(`{3,}|~{3,})', line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        heading = re.match(r'^(#{1,6})\s+\S', line)
        if heading:
            level = len(heading.group(1))
            if level == 1:
                h1 += 1
            if prev_level and level > prev_level + 1:
                errors.append((i, f"标题跳级：H{prev_level} → H{level}"))
            prev_level = level

        if re.search(r'<img\b', line, re.I):
            errors.append((i, "博客不要用 <img>，改用 ![图注](路径)"))
        if WIDTH_RE.search(line) or re.search(r'!\[[^\]]*\]\([^)]*\)\s*\{?width=', line, re.I):
            errors.append((i, "图片不要写 width 属性"))

        for m in STAMP.finditer(line):
            stamps += 1
            label = m.group(1)
            url = m.group(2)
            t = re.search(r'[?&]t=(\d+)', url)
            if not t:
                errors.append((i, f"时间戳链接缺 t 参数：{m.group(0)}"))
                continue
            shown = seconds(label)
            linked = int(t.group(1))
            if shown != linked:
                errors.append((i, f"时间戳 {label} 与 t={linked} 不一致"))
            unique.add(linked)

    if h1 != 1:
        errors.append((1, f"H1 数量为 {h1}，应为 1"))
    if len(unique) < 10:
        errors.append((1, f"独立时间点仅 {len(unique)} 个，至少 10 个"))
    return {"file": file, "stamps": stamps, "unique": len(unique), "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description="检查博客的时间戳、标题层级与图片写法。")
    parser.add_argument("paths", nargs="+", help="博客 Markdown 文件或目录")
    args = parser.parse_args()

    files = []
    for raw in args.paths:
        p = Path(raw)
        if not p.exists():
            print(f"路径不存在：{raw}", file=sys.stderr)
            return 2
        files.extend(walk(p) if p.is_dir() else [p])
    files.sort()

    bad = 0
    for f in files:
        r = check_file(f)
        if not r["errors"]:
            continue
        bad += 1
        print(f"\n📄 {f}")
        print(f"   时间戳 {r['stamps']} 个（独立 {r['unique']} 个），问题 {len(r['errors'])} 处")
        for line, msg in r["errors"][:12]:
            print(f"   ❌ L{line} {msg}")

    print(f"\n合计：{len(files)} 个文件，{bad} 个有问题")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
