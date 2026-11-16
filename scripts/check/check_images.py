#!/usr/bin/env python3
"""校验 Markdown 里的图片引用。

用法：
    python3 scripts/check/check_images.py content/K8s集群
    python3 scripts/check/check_images.py content/x/blog/某篇.md
    python3 scripts/check/check_images.py content --quiet
    python3 scripts/check/check_images.py content --list-orphans

检查项（前四项会让退出码变 1）：
  1. 引用的图片按相对路径能在磁盘上找到（兼容 %20/%29 与 <...> 写法）；
  2. 是普通文件、不是 0 字节；
  3. 扩展名与实际文件头一致；
  4. 扩展名在发布白名单内。

另外提示：未被任何文章引用的孤儿图、不会上站的扩展名。
只传单个 .md 文件时不做孤儿检查。

退出码：0 = 通过；1 = 有缺失/空文件/格式不符；2 = 用法错误。
"""

import argparse
import os
import posixpath
import re
import sys
from pathlib import Path
from urllib.parse import unquote

ASSET_EXTS = {
    ".webp", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".avif", ".bmp", ".ico", ".pdf",
}
IMAGE_EXTS = ASSET_EXTS - {".pdf"}
EXT_FORMAT = {
    ".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg", ".gif": "gif",
    ".webp": "webp", ".avif": "avif", ".bmp": "bmp", ".ico": "ico", ".svg": "svg",
}

IMG_RE = re.compile(
    r'!\[[^\]]*\]\(\s*(<[^>]*>|(?:[^()\n]|\([^()\n]*\))*?)(?:\s+"[^"]*")?\s*\)'
)
IMG_TAG_RE = re.compile(r'<img\b[^>]*?\bsrc\s*=\s*["\']([^"\']+)["\']', re.I)
SCHEME_RE = re.compile(r'^[a-zA-Z][a-zA-Z0-9+.\-]*:')
SVG_RE = re.compile(
    r'^\ufeff?\s*(<\?xml[\s\S]*?\?>\s*)?(<!--[\s\S]*?-->\s*)*'
    r'(<!DOCTYPE[\s\S]*?>\s*)?<svg',
    re.I,
)


def is_external(target: str) -> bool:
    return (
        not target
        or target.startswith("#")
        or target.startswith("//")
        or target.startswith("/")
        or bool(SCHEME_RE.match(target))
    )


def mask_code(text: str) -> list[str]:
    """把围栏代码块和行内代码挖空，保留行数，行号不变。"""
    lines = text.split("\n")
    result = []
    in_fence = False
    mark = ""
    for line in lines:
        m = re.match(r'^\s*(`{3,}|~{3,})', line)
        if not in_fence and m:
            in_fence = True
            mark = m.group(1)
            result.append("")
            continue
        if in_fence:
            if m and m.group(1)[0] == mark[0] and len(m.group(1)) >= len(mark):
                in_fence = False
            result.append("")
            continue
        result.append(re.sub(r'`[^`\n]*`', '', line))
    return result


def candidates(target: str) -> list[str]:
    """目标 -> 候选相对路径。先按 # 切锚点，再解码百分号编码。"""
    specs = []
    hash_pos = target.find("#")
    if hash_pos >= 0:
        specs.extend([target[:hash_pos], target])
    else:
        specs.append(target)
    out = []
    for spec in specs:
        decoded = unquote(spec)
        norm = posixpath.normpath(decoded.replace("\\", "/"))
        if norm not in out:
            out.append(norm)
    return out


def sniff(file: Path) -> str:
    try:
        with file.open("rb") as f:
            b = f.read(512)
    except OSError:
        return "unknown"
    if len(b) >= 8 and b[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if len(b) >= 3 and b[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if len(b) >= 6 and b[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if len(b) >= 12 and b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "webp"
    if len(b) >= 12 and b[4:8] == b"ftyp" and b[8:12] in (b"avif", b"avis"):
        return "avif"
    if len(b) >= 2 and b[:2] == b"BM":
        return "bmp"
    if len(b) >= 4 and b[:4] == b"\x00\x00\x01\x00":
        return "ico"
    if b[:4] == b"%PDF":
        return "pdf"
    if SVG_RE.match(b.decode("utf-8", "ignore")):
        return "svg"
    return "unknown"


def walk(root: Path) -> tuple[list[Path], list[Path]]:
    md, img = [], []
    for current, dirs, names in os.walk(root):
        dirs.sort()
        for name in sorted(names):
            p = Path(current) / name
            ext = p.suffix.lower()
            if ext == ".md":
                md.append(p)
            elif ext in IMAGE_EXTS:
                img.append(p)
    return md, img


def rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(p)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="检查 Markdown 图片引用、文件格式与孤儿图。",
        add_help=True,
    )
    parser.add_argument("paths", nargs="+", help="Markdown 文件或目录")
    parser.add_argument("--quiet", action="store_true", help="只输出合计")
    parser.add_argument("--list-orphans", action="store_true", help="只输出孤儿图路径")
    args = parser.parse_args()

    quiet = args.quiet or args.list_orphans
    scan_orphans = False
    md_files: list[Path] = []
    image_files: list[Path] = []

    for raw in args.paths:
        p = Path(raw)
        if not p.exists():
            print(f"路径不存在：{raw}", file=sys.stderr)
            return 2
        if p.is_dir():
            scan_orphans = True
            found_md, found_img = walk(p)
            md_files.extend(found_md)
            image_files.extend(found_img)
        else:
            md_files.append(p)

    files = sorted(set(md_files))
    seen: dict[str, str] = {}
    problems: dict[str, dict] = {}
    ref_count = 0

    for md in files:
        lines = mask_code(md.read_text(encoding="utf-8"))
        directory = md.parent
        for lineno, line in enumerate(lines, 1):
            targets = [m.group(1) for m in IMG_RE.finditer(line)]
            targets += [m.group(1) for m in IMG_TAG_RE.finditer(line)]
            for target in targets:
                target = target.strip()
                if target.startswith("<") and target.endswith(">"):
                    target = target[1:-1].strip()
                if is_external(target):
                    continue
                ref_count += 1

                resolved = None
                tried = []
                for cand in candidates(target):
                    for p in (Path(directory, cand).resolve(), Path(cand).resolve()):
                        tried.append(p)
                        if p.exists():
                            resolved = p
                            break
                    if resolved:
                        break

                ref = f"{md}:{lineno}"
                if not resolved:
                    key = str(tried[0]) if tried else target
                    problems.setdefault(key, {
                        "kind": "missing",
                        "detail": f"目标 {target}",
                        "ref": ref,
                    })
                    continue
                key = str(resolved)
                if key in seen:
                    continue
                seen[key] = ref

                if not resolved.is_file():
                    problems[key] = {"kind": "notfile", "detail": "目标是目录，不是文件", "ref": ref}
                    continue
                if resolved.stat().st_size == 0:
                    problems[key] = {"kind": "empty", "detail": "文件为 0 字节", "ref": ref}
                    continue
                ext = resolved.suffix.lower()
                if ext not in ASSET_EXTS:
                    problems[key] = {
                        "kind": "unpublished",
                        "detail": f"扩展名 {ext or '(无)'} 不在发布白名单，构建后不会上站",
                        "ref": ref,
                    }
                    continue
                if ext not in EXT_FORMAT:
                    continue
                real = sniff(resolved)
                if real != EXT_FORMAT[ext]:
                    problems[key] = {
                        "kind": "format",
                        "detail": f"扩展名 {ext}，实际是 {real if real == 'unknown' else real.upper()}",
                        "ref": ref,
                    }

    orphans = sorted(
        (p for p in image_files if str(p.resolve()) not in seen),
        key=lambda p: str(p),
    )
    orphan_bytes = sum(p.stat().st_size for p in orphans if p.exists())

    def mb(n: int) -> str:
        return f"{n / 1024 / 1024:.1f} MB"

    order = ["missing", "notfile", "empty", "format", "unpublished"]
    labels = {
        "missing": "❌ 文件不存在",
        "notfile": "❌ 不是文件（是个目录）",
        "empty": "❌ 0 字节",
        "format": "❌ 格式与扩展名不符",
        "unpublished": "⚠️  不会上站（扩展名不在发布白名单）",
    }

    if not quiet:
        for kind in order:
            items = [(k, v) for k, v in problems.items() if v["kind"] == kind]
            if not items:
                continue
            print(f"\n{labels[kind]}（{len(items)}）")
            for file, info in items[:30]:
                print(f"   {info['ref']}")
                print(f"      {rel(Path(file))}")
                print(f"      {info['detail']}")
            if len(items) > 30:
                print(f"   …另有 {len(items) - 30} 条")
        if orphans:
            print(f"\n⚠️  存在但没被任何文章引用（{len(orphans)} 个，共 {mb(orphan_bytes)}；可删除或挪到别处）")
            for p in orphans[:30]:
                print(f"   {rel(p)}  ({p.stat().st_size // 1024} KB)")
            if len(orphans) > 30:
                print(f"   …另有 {len(orphans) - 30} 条")

    def count(kind: str) -> int:
        return sum(1 for v in problems.values() if v["kind"] == kind)

    if args.list_orphans:
        for p in orphans:
            print(p)
        return 0

    summary = (
        f"\n合计：{len(files)} 个 .md，图片引用 {ref_count} 处"
        f"，缺失 {count('missing')}，非文件 {count('notfile')}，空文件 {count('empty')}"
        f"，格式不符 {count('format')}"
        f"，未发布 {count('unpublished')}"
    )
    if scan_orphans:
        summary += f"，未被引用 {len(orphans)}（{mb(orphan_bytes)}）"
    print(summary)

    hard = count("missing") + count("notfile") + count("empty") + count("format")
    return 0 if hard == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
