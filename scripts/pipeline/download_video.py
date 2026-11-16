#!/usr/bin/env python3
"""用 yt-dlp 下载视频（仅视频流，供抽帧用），支持断点续传。

统一 Bilibili / YouTube 的下载入口，内部调用 ``python -m yt_dlp``：
  - 只下视频流、不要音频：字幕来自在线服务，不需要音视频合并（无需 ffmpeg）。
  - 编码优先 avc1/H.264（OpenCV 解码最稳），该高度没有 avc1 时回退到其他编码
    （此时文件可能大很多，可用 --height 降低）。
  - yt-dlp 默认支持断点续传（.part 文件）；注意**换格式后旧 .part 会失效**
    （HTTP 416），需删除 *.part 后重下。

目录约定：每个视频一个以 ``--bv``（视频 ID）命名的子目录，多个视频天然共存：
    <workdir>/videos/<视频ID>.mp4

用法:
    python download_video.py --workdir <dir> --bv BV1xxxx [--height 1080]
    python download_video.py --platform youtube --bv dQw4w9WgXcQ --workdir <dir>
"""
from __future__ import annotations

import argparse
import glob
import os
import subprocess
import sys


def _force_utf8_stdio() -> None:
    """Windows/Git Bash（GBK）下把中文输出统一为 UTF-8，避免乱码。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


# 支持的平台：视频页 URL 模板
PLATFORM_URLS = {
    "bilibili": "https://www.bilibili.com/video/{video_id}/",
    "youtube": "https://www.youtube.com/watch?v={video_id}",
}


def build_download_cmd(platform: str, video_id: str, workdir: str, height: int) -> list[str]:
    """构造 yt-dlp 下载命令；输出为 <workdir>/videos/<视频ID>.mp4。"""
    url = PLATFORM_URLS[platform].format(video_id=video_id)
    # 优先该高度内的 avc1（H.264，OpenCV 兼容性最好）；没有则回退任意编码
    video_format = f"bv*[height<={height}][vcodec^=avc1]/bv*[height<={height}]"
    return [
        sys.executable, "-m", "yt_dlp", "--no-warnings", "--newline", "--progress",
        "-f", video_format,
        "-o", os.path.join(workdir, "videos", f"{video_id}.%(ext)s"),
        url,
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="下载单个视频流（yt-dlp 封装，支持续传）")
    parser.add_argument("--workdir", required=True,
                        help="工作目录（视频存到 <workdir>/videos/<视频ID>.mp4）")
    parser.add_argument("--bv", required=True,
                        help="视频 ID：B 站为 BV 号，YouTube 为 11 位视频 ID")
    parser.add_argument("--platform", default="bilibili", choices=sorted(PLATFORM_URLS),
                        help="视频平台，默认 bilibili")
    parser.add_argument("--height", type=int, default=1080,
                        help="最大分辨率高度，默认 1080；体积过大可降到 720")
    return parser.parse_args()


def find_output(workdir: str, video_id: str) -> str | None:
    """返回下载产物路径（忽略 .part 等临时文件），找不到则 None。"""
    matches = [p for p in glob.glob(os.path.join(workdir, "videos", f"{video_id}.*"))
               if not p.endswith(".part")]
    return matches[0] if matches else None


def main() -> None:
    _force_utf8_stdio()
    args = parse_args()
    cmd = build_download_cmd(args.platform, args.bv, args.workdir, args.height)
    print(">", " ".join(cmd))
    return_code = subprocess.call(cmd)
    if return_code == 0:
        output = find_output(args.workdir, args.bv)
        if output:
            size_mb = os.path.getsize(output) / (1024 * 1024)
            print(f"下载完成: {output} ({size_mb:.1f} MB)")
        else:
            print("下载完成，但未找到输出文件（请检查 --bv 与 videos/ 目录）")
    else:
        print(f"下载失败（yt-dlp 退出码 {return_code}）；"
              f"可尝试降分辨率 --height 720，或先删除 videos/*.part 后重试")
    raise SystemExit(return_code)


if __name__ == "__main__":
    main()
