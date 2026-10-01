#!/usr/bin/env python3
"""用 OpenCV 对视频按固定间隔抽帧（默认每秒 1 张）。

产物与约定：
  - 输出到 ``<workdir>/frames/<视频ID>/``，文件名 ``00000.jpg`` 对应第 0 秒，
    即「编号 = 秒数」，与 build_transcript.py、transcripts/img 的命名一致。
  - 用 ``grab()`` 跳过不需要的帧、只对目标帧 ``retrieve()``，比逐帧解码快得多。
  - 若输出目录已有超过 10 张帧图，视为已完成，跳过（``--force`` 可强制重跑）。

依赖：``pip install opencv-python numpy``

用法:
    python extract_frames.py --workdir <dir> --bv BV1xxxx [--fps 1] [--width 0] [--quality 100]
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
import time
from dataclasses import dataclass

try:
    import cv2
except ImportError:  # OpenCV 缺失时保留 import，让 main() 给出友好报错
    cv2 = None  # type: ignore[assignment]


def _force_utf8_stdio() -> None:
    """Windows/Git Bash（GBK）下把中文输出统一为 UTF-8，避免乱码。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


@dataclass(frozen=True)
class ExtractOptions:
    """抽帧参数。"""

    workdir: str
    fps: float = 1.0
    width: int = 0     # 缩放宽度；0 表示保留原始尺寸（默认不缩放）
    quality: int = 100  # JPEG 质量 0-100
    force: bool = False


def extract_frames(video_path: str, out_dir: str, options: ExtractOptions) -> int:
    """从单个视频抽帧，返回保存的帧数。

    编号与时间对齐：源视频按 ``source_fps`` 播放，每 ``step = source_fps / options.fps``
    帧取一张，因此第 k 张保存的帧对应第 ``k / options.fps`` 秒（默认 1fps 时即文件名编号=秒数）。
    """
    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        print(f"无法打开视频（格式不受支持？）: {video_path}")
        return 0

    source_fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(source_fps / options.fps))
    start_time = time.time()
    saved_count = 0
    frame_index = 0

    while True:
        # grab() 只解码不取数据，跳过帧几乎零成本
        if not capture.grab():
            break
        if frame_index % step == 0:
            ok, frame = capture.retrieve()
            if not ok:
                break
            resized = _resize_if_needed(frame, options.width)
            output_path = os.path.join(out_dir, f"{saved_count:05d}.jpg")
            cv2.imwrite(
                output_path,
                resized,
                [int(cv2.IMWRITE_JPEG_QUALITY), options.quality],
            )
            saved_count += 1
        frame_index += 1

    capture.release()
    elapsed = time.time() - start_time
    print(f"{video_path}: source_fps={source_fps:.3f} saved={saved_count} "
          f"{elapsed:.0f}s -> {out_dir}")
    return saved_count


def _resize_if_needed(frame, target_width: int):
    """按目标宽度等比缩放帧；target_width<=0 时原样返回。"""
    if target_width <= 0:
        return frame
    height = int(frame.shape[0] * target_width / frame.shape[1])
    return cv2.resize(frame, (target_width, height), interpolation=cv2.INTER_AREA)


def extract_frames_for_video(options: ExtractOptions, video_id: str) -> None:
    """抽帧 videos/<视频ID>.mp4 -> frames/<视频ID>/；视频缺失或缺帧图不足时提示。"""
    video_path = os.path.join(options.workdir, "videos", video_id + ".mp4")
    out_dir = os.path.join(options.workdir, "frames", video_id)

    if not os.path.exists(video_path):
        print(f"缺少视频 {video_path}")
        return
    os.makedirs(out_dir, exist_ok=True)

    # 已抽过帧就跳过，避免长视频重复跑几分钟
    existing_frames = glob.glob(os.path.join(out_dir, "*.jpg"))
    if len(existing_frames) > 10 and not options.force:
        print(f"已存在（{len(existing_frames)} 帧），跳过；--force 可强制重跑")
        return

    extract_frames(video_path, out_dir, options)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按固定间隔（默认 1fps）对视频抽帧")
    parser.add_argument("--workdir", required=True,
                        help="工作目录（视频为 videos/<视频ID>.mp4，帧存到 frames/<视频ID>/）")
    parser.add_argument("--bv", required=True,
                        help="视频 ID：B 站为 BV 号，YouTube 为 11 位视频 ID")
    parser.add_argument("--fps", type=float, default=1, help="抽帧频率（帧/秒），默认 1")
    parser.add_argument("--width", type=int, default=0,
                        help="缩放宽度，0 表示保留原始尺寸（默认）")
    parser.add_argument("--quality", type=int, default=100,
                        help="JPEG 质量 0-100，默认 100（不额外压缩画质）")
    parser.add_argument("--force", action="store_true", help="忽略已有帧，强制重跑")
    return parser.parse_args()


def main() -> None:
    _force_utf8_stdio()
    if cv2 is None:
        raise SystemExit("缺少 OpenCV，请先安装：pip install opencv-python numpy")
    args = parse_args()
    options = ExtractOptions(
        workdir=args.workdir,
        fps=args.fps,
        width=args.width,
        quality=args.quality,
        force=args.force,
    )
    extract_frames_for_video(options, args.bv)


if __name__ == "__main__":
    main()
