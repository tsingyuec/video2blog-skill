#!/usr/bin/env python3
"""分栏文稿窗口文本的「导出 ↔ 写回」工具 —— 文稿通顺化循环的两端。

与 transcripts/<视频标题>.md（Markdown 表格分栏版）配合使用：

    # 1) 导出某时间区间的窗口文本，每行形如 01202|窗口原文
    python transcript_windows.py dump transcripts/p08.md 1202 1700

    # 2) 逐窗口改写后，把 NNNN|改写后文本 从 stdin 喂回（⚠️ heredoc 必须写结束分隔符）
    python transcript_windows.py apply transcripts/p08.md << 'REWRITE'
    01202|改写后的文本……
    REWRITE

文稿行格式约定（由 build_transcript.py 生成）：
    | 字幕文本 [【跳转到 MM:SS】](url) | <img src="img/<视频ID>/SSSSS.jpg" width="9000"> |

其中 SSSSS = 窗口起点秒，既是图片文件名也是窗口号（5 位，00000 = 第 0 秒）。
"""
from __future__ import annotations

import argparse
import re
import sys

# 右栏代表帧路径，如 img/BV1xx411c7mD/00754.jpg —— 编号即窗口起点秒
FRAME_REF_PATTERN = re.compile(r"img/[^/]+/(\d+)\.jpg")
# 左栏文本与时间戳链接的分隔符（"[" 与 "【" 之间无空格）
JUMP_LINK_PREFIX = " [【跳转到"
JUMP_LINK_TAIL_PATTERN = re.compile(r" ?\[【跳转到[^\]]*\]\([^)]*\)")
IMG_CELL_PATTERN = re.compile(r"\| <img [^>]+> \|$")
WINDOW_ID_PATTERN = re.compile(r"\d{5}")


# ---------------------------------------------------------------- 共享：窗口行识别
def _force_utf8_stdio() -> None:
    """Windows/Git Bash（GBK）下把中文输出统一为 UTF-8，避免乱码。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def _iter_window_rows(lines: list[str]):
    """依次产出 (行下标, 窗口号 5 位字符串)。只覆盖含时间戳链接的左栏行。

    每遇到右栏帧图即更新当前窗口号；一个窗口号只产出一次，与
    build_transcript.py 的"每窗口一行"格式一一对应。
    """
    current_window: str | None = None
    for index, line in enumerate(lines):
        frame_match = FRAME_REF_PATTERN.search(line)
        if frame_match:
            current_window = f"{int(frame_match.group(1)):05d}"
        if line.startswith("| ") and JUMP_LINK_PREFIX in line and current_window is not None:
            yield index, current_window
            current_window = None


# ---------------------------------------------------------------- dump 子命令
def dump_windows(transcript_path: str, start_sec: int, end_sec: int,
                 output_path: str | None = None) -> int:
    """把 ``[start_sec, end_sec)`` 区间的窗口行输出，返回导出数。

    每行输出 ``NNNNN|窗口文本``，NNNNN 即 apply 子命令所需的窗口号。
    区间按窗口号（= 起点秒）比较，``start_sec``/``end_sec`` 单位都是秒（左闭右开）。
    未指定 ``output_path`` 时写到 stdout。
    """
    exported = 0
    with open(transcript_path, encoding="utf-8") as f:
        lines = f.read().split("\n")

    out = (open(output_path, "w", encoding="utf-8", newline="\n")
           if output_path else sys.stdout)
    try:
        for _, window_id, line in ((i, w, lines[i]) for i, w in _iter_window_rows(lines)):
            if not (start_sec <= int(window_id) < end_sec):
                continue
            # 去掉行首 "| " 与其后整段时间戳链接，只留字幕文本
            text = line.split(JUMP_LINK_PREFIX)[0][2:]
            print(f"{window_id}|{text}", file=out)
            exported += 1
    finally:
        if output_path:
            out.close()
    return exported


# ---------------------------------------------------------------- apply 子命令
def _read_stdin_text() -> str:
    """读取 stdin，优先按 utf-8 解码，失败则回退 gbk。

    Windows + Git Bash 下终端默认 GBK，而 heredoc 内容往往是 utf-8 字节，
    用 locale 直接解码会产生乱码或代理字符，因此从 buffer 读取并显式解码。
    """
    raw = sys.stdin.buffer.read() if sys.stdin.buffer else sys.stdin.read().encode("utf-8")
    for encoding in ("utf-8", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def read_window_rewrites(stdin_text: str) -> dict[str, str]:
    """从 stdin 文本解析 ``NNNNN|新文本`` 行，返回 {窗口号: 新文本}。

    - 行内第一个 "|" 是分隔符，其后全部算作新文本。
    - 空行与不以 5 位数字开头的行忽略。
    - 新文本中的 "|" 会破坏 MD 表格，自动转义为 "\\|"。
    """
    mapping: dict[str, str] = {}
    for raw_line in stdin_text.split("\n"):
        line = raw_line.strip()
        if "|" not in line:
            continue
        window_id, new_text = line.split("|", 1)
        window_id = window_id.strip()
        if not WINDOW_ID_PATTERN.fullmatch(window_id):
            continue
        mapping[window_id] = new_text.replace("|", "\\|")
    return mapping


def apply_rewrites(transcript_path: str, mapping: dict[str, str]
                   ) -> tuple[int, list[str], int]:
    """把 mapping 中的新文本写回文稿左栏。

    只替换左栏字幕文本；时间戳跳转链接与右栏 <img> 原样保留。
    返回 ``(成功替换数, 未匹配的窗口号列表, 文稿窗口总数)``。未匹配指
    mapping 里有、但文稿中找不到对应窗口行（通常是窗口号抄错或文件不符）。
    """
    with open(transcript_path, encoding="utf-8") as f:
        lines = f.read().split("\n")

    window_ids = [window_id for _, window_id in _iter_window_rows(lines)]
    window_id_set = set(window_ids)
    applied = 0
    for index, window_id in _iter_window_rows(lines):
        new_text = mapping.get(window_id)
        if new_text is None:
            continue
        lines[index] = _rewrite_row(lines[index], new_text)
        applied += 1

    with open(transcript_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    unmatched = sorted(window_id for window_id in mapping if window_id not in window_id_set)
    return applied, unmatched, len(window_ids)


def _rewrite_row(line: str, new_text: str) -> str:
    """替换一行左栏文本，保留其后整段链接与 <img> 单元格。

    原行: `| {old_text} [【跳转到..】](url) | <img ..> |`
    新行: `| {new_text}{link} | <img ..> |`
    """
    tail_match = JUMP_LINK_TAIL_PATTERN.search(line)
    link = tail_match.group(0) if tail_match else ""
    img_match = IMG_CELL_PATTERN.search(line)
    img_cell = img_match.group(0) if img_match else ""  # 保留作为列分隔的 "|"
    return f"| {new_text}{link} {img_cell}".rstrip()


# ---------------------------------------------------------------- CLI
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="分栏文稿窗口文本的导出（dump）与写回（apply）")
    subparsers = parser.add_subparsers(dest="command", required=True)

    dump_parser = subparsers.add_parser("dump", help="导出某时间区间的窗口文本")
    dump_parser.add_argument("transcript", help="文稿路径，如 transcripts/p08.md")
    dump_parser.add_argument("start", type=int, help="起始秒（含，按窗口起点秒比较）")
    dump_parser.add_argument("end", type=int, help="结束秒（不含）")
    dump_parser.add_argument("--out", help="写入文件（缺省打印到 stdout）")
    dump_parser.add_argument("--quiet", action="store_true", help="不打印导出统计行")

    apply_parser = subparsers.add_parser(
        "apply", help="从 stdin 读 NNNNN|新文本 并写回文稿")
    apply_parser.add_argument("transcript", help="文稿路径，如 transcripts/p08.md")

    return parser.parse_args()


def main() -> None:
    _force_utf8_stdio()
    args = parse_args()
    if args.command == "dump":
        count = dump_windows(args.transcript, args.start, args.end, args.out)
        if not args.quiet:
            print(f"# 共导出 {count} 个窗口", file=sys.stderr)
        return

    mapping = read_window_rewrites(_read_stdin_text())
    if not mapping:
        print("stdin 中没有解析到任何 'NNNNN|新文本' 行（注意 heredoc 要写结束分隔符）")
        raise SystemExit(1)
    applied, unmatched, total = apply_rewrites(args.transcript, mapping)
    message = f"已写回 {applied}/{len(mapping)} 个窗口（文稿共 {total} 个窗口）"
    if unmatched:
        message += f"；未匹配: {', '.join(unmatched)}"
    print(message)


if __name__ == "__main__":
    main()
