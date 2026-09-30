"""用 OpenCV 抽帧（默认每秒 1 张）。

- 帧号 = 秒数 + 1：`00001.jpg` 对应第 0 秒，与 `build_transcript.py` 的时间对齐一致。
- 用 `grab()` 跳过不需要的帧、只 `retrieve()` 需要的帧，速度足够快。
- 依赖：`pip install opencv-python numpy`

用法:
  python extract_frames.py --workdir <dir> --parts 1,2,3 [--fps 1] [--width 960] [--quality 85]
"""
import argparse, glob, os, time

try:
    import cv2
except ImportError:  # noqa
    cv2 = None


def extract(part, args):
    p = f"p{part:02d}"
    src = os.path.join(args.workdir, "videos", p + ".mp4")
    outdir = os.path.join(args.workdir, "frames", p)
    if not os.path.exists(src):
        print(f"{p}: 缺少视频 {src}")
        return
    os.makedirs(outdir, exist_ok=True)
    if len(glob.glob(os.path.join(outdir, "*.jpg"))) > 10 and not args.force:
        print(f"{p}: 已存在，跳过")
        return

    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        print(f"{p}: 无法打开视频（格式不受支持？）")
        return
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(fps / args.fps))  # 每隔 step 帧取一张
    t0, saved, idx = time.time(), 0, 0
    while True:
        if not cap.grab():
            break
        if idx % step == 0:
            ok, frame = cap.retrieve()
            if not ok:
                break
            if args.width:
                w = args.width
                h = int(frame.shape[0] * w / frame.shape[1])
                frame = cv2.resize(frame, (w, h), interpolation=cv2.INTER_AREA)
            cv2.imwrite(
                os.path.join(outdir, f"{saved + 1:05d}.jpg"),
                frame,
                [int(cv2.IMWRITE_JPEG_QUALITY), args.quality],
            )
            saved += 1
        idx += 1
    cap.release()
    print(f"{p}: fps={fps:.3f} saved={saved} {time.time() - t0:.0f}s -> {outdir}")


def main():
    if cv2 is None:
        raise SystemExit("缺少 OpenCV，请先安装：pip install opencv-python numpy")
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--parts", required=True, help="如 1,2,3")
    ap.add_argument("--fps", type=float, default=1)
    ap.add_argument("--width", type=int, default=960, help="缩放宽度，0 表示原始尺寸")
    ap.add_argument("--quality", type=int, default=85, help="JPEG 质量 0-100，越大越清晰")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    for part in [int(x) for x in args.parts.split(",")]:
        extract(part, args)


if __name__ == "__main__":
    main()
