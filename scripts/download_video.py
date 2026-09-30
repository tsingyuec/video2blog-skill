#!/usr/bin/env python3
"""用 yt-dlp 下载视频（仅视频流，供抽帧用），支持断点续传。

统一 B 站 / YouTube 的下载入口，内部调用 ``python -m yt_dlp``：
  - 只下视频流、不要音频：字幕来自在线服务，不需要音视频合并（无需 ffmpeg）。
  - 编码优先 avc1/H.264（OpenCV 解码最稳），该高度没有 avc1 时回退到其他编码
    （此时文件可能大很多，可用 --height 降低）。
  - yt-dlp 默认支持断点续传（.part 文件）；注意**换格式后旧 .part 会失效**
    （HTTP 416），需删除 videos/*.part 后重下。

用法:
    python download_video.py --workdir <dir> --bv BV1xxxx --parts 1,2,3 [--height 1080]
    python download_video.py --platform youtube --bv dQw4w9WgXcQ --workdir <dir>
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

# 支持的平台：视频 URL 模板 与 分 P 语义
#   bilibili: --parts 指定分 P 区间（playlist_index 由 yt-dlp 提供）
#   youtube:  单视频，固定 1 个"分 P"（p01），与流水线的 pNN 目录约定对齐
PLATFORM_URLS = {
    "bilibili": "https://www.bilibili.com/video/{video_id}/",
    "youtube": "https://www.youtube.com/watch?v={video_id}",
}


def resolve_parts(platform: str, parts_arg: str) -> list[int]:
    """把 --parts 解析为分 P 列表：B 站按逗号展开，YouTube 固定为 [1]。

    流水线内部统一按分 P（pNN）组织目录；YouTube 没有多 P 概念，
    固定映射为单个分 P，使两个平台共享同一套目录/文件命名。
    """
    if platform == "bilibili":
        return [int(p.strip()) for p in parts_arg.split(",")]
    return [1]


def build_download_cmd(platform: str, video_id: str, workdir: str,
                       height: int, parts: list[int]) -> list[str]:
    """构造 yt-dlp 命令行。"""
    url = PLATFORM_URLS[platform].format(video_id=video_id)
    # 优先该高度内的 avc1（H.264，OpenCV 兼容性最好）；没有则回退任意编码
    video_format = f"bv*[height<={height}][vcodec^=avc1]/bv*[height<={height}]"
    cmd = [sys.executable, "-m", "yt_dlp", "-q", "--no-warnings",
           "-f", video_format]

    if platform == "bilibili":
        # 多 P 一起下，用 -I 圈定范围；单 P 时 playlist_index 会变成 NA，
        # 因此总是按区间整段下载，由 yt-dlp 命名 pNN
        first, last = min(parts), max(parts)
        cmd += ["-o", os.path.join(workdir, "videos", "p%(playlist_index)02d.%(ext)s"),
                "-I", f"{first}:{last}"]
    else:
        # YouTube 单视频固定命名 p01
        cmd += ["-o", os.path.join(workdir, "videos", "p01.%(ext)s")]

    cmd.append(url)
    return cmd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="下载视频流（yt-dlp 封装，支持续传）")
    parser.add_argument("--workdir", required=True, help="工作目录（视频存到 videos/）")
    parser.add_argument("--bv", required=True,
                        help="视频 ID：B 站为 BV 号，YouTube 为 11 位视频 ID")
    parser.add_argument("--platform", default="bilibili", choices=sorted(PLATFORM_URLS),
                        help="视频平台，默认 bilibili")
    parser.add_argument("--parts", default="1",
                        help="B 站分 P 列表，如 1,2,3（YouTube 忽略此参数）")
    parser.add_argument("--height", type=int, default=1080,
                        help="最大分辨率高度，默认 1080；体积过大可降到 720")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    parts = resolve_parts(args.platform, args.parts)
    cmd = build_download_cmd(args.platform, args.bv, args.workdir, args.height, parts)
    print(">", " ".join(cmd))
    raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
