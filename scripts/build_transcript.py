#!/usr/bin/env python3
"""生成「图片-字幕」原始文稿 —— 本工作流的核心工件。

处理**单个视频**（统一映射为分 P ``p01``；多个视频对每个视频重复调用本脚本）：
  1) 若 ``subs/kedou_NN.json``（subtitle_fetch.py 的输出）存在，先导出
     ``subs/pNN.srt`` 与 ``subs/pNN.txt``；
  2) 对 ``frames/pNN/`` 的 1fps 抽帧按「画面变化」切分时间窗口
     （帧缩到 32x18 灰度，与窗口代表帧做平均绝对差）；
  3) 每个窗口保留一张代表帧并合并窗口内字幕，输出 ``transcripts/pNN.md``
     （Markdown 表格分栏，含可点击时间戳）。

⚠️ 通顺化改写（dump_windows/apply_windows 循环）之后不要再运行本脚本，
   否则会覆盖已改写的文稿。

用法:
    python build_transcript.py --workdir <dir> --bv BV1xxxx --title "视频标题" \\
        --parts 1,2,3 --diff 12 --minwin 5 --maxwin 25
    python build_transcript.py --platform youtube --bv dQw4w9WgXcQ --title "标题" \
        --parts 1 --workdir <dir>
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
from dataclasses import dataclass

import numpy as np
from PIL import Image

# 画面差异比较用的缩略图尺寸（宽 x 高）
THUMBNAIL_SIZE = (32, 18)
# 无字幕且短于该秒数的窗口直接丢弃（多为转场/空屏）
MIN_KEPT_WINDOW_SEC = 3

# 时间戳跳转链接构造规则：{t} 为窗口起点秒（YouTube 的 t=秒数 同样有效）
JUMP_URL_BUILDERS = {
    "bilibili": lambda video_id, t: f"https://www.bilibili.com/video/{video_id}/?t={t}",
    "youtube": lambda video_id, t: f"https://www.youtube.com/watch?v={video_id}&t={t}",
}


@dataclass
class WindowingOptions:
    """时间窗口切分参数（经验值 --diff 12 --minwin 5 --maxwin 25 适合课堂幻灯片）。"""

    diff_threshold: float  # 与当前代表帧的平均绝对差超过该值 → 视为画面变化
    min_window_sec: int    # 距窗口起点不足该秒数时，即使画面变化也不切分
    max_window_sec: int    # 同画面停留超过该秒数时强制切一刀


@dataclass
class Window:
    """一个时间窗口：起点秒、代表帧路径。窗口终点由下一个窗口的起点决定。"""

    start_sec: int
    frame_path: str


# ---------------------------------------------------------------- 字幕导出与解析
def export_srt_from_kedou_json(workdir: str, video_id: str) -> None:
    """把 subs/kedou_<视频ID>.json（subtitle_fetch.py 的输出）导出为
    subs/p01.srt 与 subs/p01.txt。

    已存在 srt 时跳过（幂等）；json 缺失或内容为空时静默返回，由后续
    流程报告「缺少字幕」。
    """
    srt_path = os.path.join(workdir, "subs", "p01.srt")
    if os.path.exists(srt_path):
        return

    json_candidates = [os.path.join(workdir, "subs", f"kedou_{video_id}.json")]
    for json_path in json_candidates:
        if not os.path.exists(json_path):
            continue
        try:
            with open(json_path, encoding="utf-8") as f:
                payload = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        subtitle_items = (payload.get("data") or {}).get("subtitleItemVoList") or []
        if not subtitle_items:
            continue

        srt_content = subtitle_items[0].get("content", "")
        os.makedirs(os.path.join(workdir, "subs"), exist_ok=True)
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt_content)
        # p01.txt：去掉序号行与时间轴行，只留字幕文本，便于通顺化时参考
        text_lines = []
        for line in srt_content.splitlines():
            stripped = line.strip()
            if not stripped or re.fullmatch(r"\d+", stripped) or "-->" in stripped:
                continue
            text_lines.append(stripped)
        txt_path = os.path.join(workdir, "subs", "p01.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(text_lines))
        return


def parse_srt(srt_path: str) -> list[tuple[float, str]]:
    """解析 SRT，返回按序的 (开始秒, 字幕文本) 列表（文本已去空白）。"""
    with open(srt_path, encoding="utf-8") as f:
        raw = f.read()

    subtitles: list[tuple[float, str]] = []
    time_pattern = re.compile(
        r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)"
    )
    for block in re.split(r"\n\s*\n", raw):
        match = time_pattern.search(block)
        if not match:
            continue
        hours, minutes, seconds, millis = map(int, match.groups()[:4])
        start_sec = hours * 3600 + minutes * 60 + seconds + millis / 1000.0
        text = re.sub(r"\s+", "", block[match.end():].strip())
        if text:
            subtitles.append((start_sec, text))
    return subtitles


# ---------------------------------------------------------------- 画面窗口切分
def load_grayscale_thumbnail(image_path: str) -> np.ndarray:
    """读图并缩到 THUMBNAIL_SIZE 的灰度 float32 数组，用于快速比较。"""
    image = Image.open(image_path).convert("L").resize(THUMBNAIL_SIZE)
    return np.asarray(image, dtype=np.float32)


def split_into_windows(frame_files: list[str], options: WindowingOptions) -> list[Window]:
    """按画面变化把 1fps 帧序列切分为时间窗口。

    规则：与当前窗口代表帧的平均绝对差 > diff_threshold 且距窗口起点
    >= min_window_sec 时开新窗口；同一画面停留 >= max_window_sec 强制切分。
    第 k 帧对应第 k 秒（帧号 = 秒数 + 1），故直接用下标作时间。
    """
    windows: list[Window] = []
    representative: np.ndarray | None = None
    window_start: int | None = None

    for timestamp, frame_path in enumerate(frame_files):
        thumbnail = load_grayscale_thumbnail(frame_path)
        if representative is None:
            representative, window_start = thumbnail, timestamp
            windows.append(Window(start_sec=timestamp, frame_path=frame_path))
            continue

        diff = float(np.mean(np.abs(thumbnail - representative)))
        start_new_window = diff > options.diff_threshold
        # 画面刚切换时抖动较大：不足 min_window_sec 不切，避免碎窗口
        if start_new_window and timestamp - window_start < options.min_window_sec:
            start_new_window = False
        # 同一张幻灯片停留太久：强制切一刀，保证窗口粒度可控
        if timestamp - window_start >= options.max_window_sec:
            start_new_window = True

        if start_new_window:
            representative, window_start = thumbnail, timestamp
            windows.append(Window(start_sec=timestamp, frame_path=frame_path))

    return windows


# ---------------------------------------------------------------- 文稿生成
def build_transcript(workdir: str, video_id: str, title: str,
                     options: WindowingOptions, platform: str = "bilibili") -> None:
    """生成 transcripts/p01.md；缺帧或缺字幕时跳过。

    video_id 仅用于时间戳跳转链接；workdir 内统一使用 p01 命名。
    """
    part_name = "p01"
    export_srt_from_kedou_json(workdir, video_id)

    frame_files = sorted(glob.glob(os.path.join(workdir, "frames", "p01", "*.jpg")))
    srt_path = os.path.join(workdir, "subs", "p01.srt")
    if not frame_files or not os.path.exists(srt_path):
        print("p01: 缺少帧或字幕，跳过")
        return
    subtitles = parse_srt(srt_path)

    windows = split_into_windows(frame_files, options)
    # 每个窗口的终点 = 下一个窗口的起点；末尾用哨兵值表示视频结尾
    window_ends = [w.start_sec for w in windows[1:]] + [10 ** 9]

    image_dir = os.path.join(workdir, "transcripts", "img", part_name)
    os.makedirs(image_dir, exist_ok=True)
    lines = [
        f"# {title} 原始文稿（图-字幕分栏）",
        "",
        "| 字幕文本 | 画面 |",
        "| :--- | ---: |",
        "",
    ]

    kept_count = 0
    for window, window_end in zip(windows, window_ends):
        # 合并落在 [window.start_sec, window_end) 内的所有字幕
        segment = "".join(
            text for start, text in subtitles if window.start_sec <= start < window_end
        )
        if not segment and window_end - window.start_sec < MIN_KEPT_WINDOW_SEC:
            continue  # 无字幕且太短的窗口（转场/空屏）直接丢弃

        timestamp_label = f"{window.start_sec // 60:02d}:{window.start_sec % 60:02d}"
        jump_url = JUMP_URL_BUILDERS[platform](video_id, window.start_sec)
        image_name = f"{window.start_sec:05d}.jpg"
        shutil.copyfile(window.frame_path, os.path.join(image_dir, image_name))
        kept_count += 1

        text = (segment if segment else "（此区间无字幕）").strip().replace("|", "\\|")
        lines.append(
            f"| {text} [【跳转到 {timestamp_label}】]({jump_url}) "
            f"| <img src=\"img/{part_name}/{image_name}\" width=\"9000\"> |"
        )

    output_path = os.path.join(workdir, "transcripts", "p01.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"p01: frames={len(frame_files)} windows={len(windows)} "
          f"kept={kept_count} -> {output_path}")


# ---------------------------------------------------------------- CLI
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成「图片-字幕」原始文稿")
    parser.add_argument("--workdir", required=True, help="工作目录")
    parser.add_argument("--bv", required=True,
                        help="视频 ID：B 站为 BV 号，YouTube 为 11 位视频 ID")
    parser.add_argument("--platform", default="bilibili", choices=sorted(JUMP_URL_BUILDERS),
                        help="视频平台（决定跳转链接格式与字幕文件名），默认 bilibili")
    parser.add_argument("--title", required=True, help="视频标题（写入文稿一级标题）")
    parser.add_argument("--diff", type=float, default=12.0,
                        help="画面差异阈值（平均绝对差），默认 12")
    parser.add_argument("--minwin", type=int, default=5,
                        help="最短窗口秒数，默认 5")
    parser.add_argument("--maxwin", type=int, default=25,
                        help="最长窗口秒数（强制切分），默认 25")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    options = WindowingOptions(
        diff_threshold=args.diff,
        min_window_sec=args.minwin,
        max_window_sec=args.maxwin,
    )

    build_transcript(args.workdir, args.bv, args.title, options, args.platform)


if __name__ == "__main__":
    main()
