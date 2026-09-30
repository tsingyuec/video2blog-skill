"""生成「图片-字幕」原始文稿。

做三件事：
  1) 若 subs/kedou_NN.json（kedou_fetch.js 的输出）存在，导出 subs/pNN.srt / pNN.txt；
  2) 对 frames/pNN/ 的 1fps 抽帧按「画面变化」切时间窗口（缩到 32x18 灰度做平均绝对差）；
  3) 每个窗口保留一张代表帧，合并该窗口内的字幕，输出 transcripts/pNN.md（含可点击时间戳）。

用法:
  python build_transcript.py --workdir <dir> --bv BV1xxxx --title "视频标题" --parts 1,2,3 \
      --diff 12 --minwin 5 --maxwin 25
"""
import argparse, glob, json, os, re, shutil
import numpy as np
from PIL import Image


def export_srt_from_json(workdir, part):
    """kedou_NN.json -> subs/pNN.srt + pNN.txt"""
    p = f"p{part:02d}"
    jpath_candidates = [
        os.path.join(workdir, "subs", f"kedou_{part:02d}.json"),
        os.path.join(workdir, "subs", f"kedou_{part}.json"),
    ]
    srt_path = os.path.join(workdir, "subs", p + ".srt")
    if os.path.exists(srt_path):
        return
    for jp in jpath_candidates:
        if not os.path.exists(jp):
            continue
        try:
            j = json.load(open(jp, encoding="utf-8"))
        except Exception:
            continue
        items = (j.get("data") or {}).get("subtitleItemVoList") or []
        if not items:
            continue
        content = items[0].get("content", "")
        os.makedirs(os.path.join(workdir, "subs"), exist_ok=True)
        open(srt_path, "w", encoding="utf-8").write(content)
        lines = []
        for line in content.splitlines():
            s = line.strip()
            if not s or re.match(r"^\d+$", s) or "-->" in s:
                continue
            lines.append(s)
        open(os.path.join(workdir, "subs", p + ".txt"), "w", encoding="utf-8").write("\n".join(lines))
        return


def parse_srt(path):
    subs = []
    raw = open(path, encoding="utf-8").read()
    for b in re.split(r"\n\s*\n", raw):
        m = re.search(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", b)
        if not m:
            continue
        h, mm, s, ms, h2, mm2, s2, ms2 = map(int, m.groups())
        start = h * 3600 + mm * 60 + s + ms / 1000.0
        text = re.sub(r"\s+", "", b[m.end():].strip())
        if text:
            subs.append((start, text))
    return subs


def frame_low(path, size=(32, 18)):
    return np.asarray(Image.open(path).convert("L").resize(size), dtype=np.float32)


def build(part, args):
    p = f"p{part:02d}"
    export_srt_from_json(args.workdir, part)
    framefiles = sorted(glob.glob(os.path.join(args.workdir, "frames", p, "*.jpg")))
    srt = os.path.join(args.workdir, "subs", p + ".srt")
    if not framefiles or not os.path.exists(srt):
        print(f"{p}: 缺少帧或字幕，跳过")
        return
    subs = parse_srt(srt)

    windows, rep, win_start = [], None, None
    for idx, f in enumerate(framefiles):
        t = idx
        low = frame_low(f)
        if rep is None:
            rep, win_start = low, t
            windows.append([t, f])
            continue
        d = float(np.mean(np.abs(low - rep)))
        newwin = d > args.diff
        if newwin and (t - win_start) < args.minwin:
            newwin = False
        if (t - win_start) >= args.maxwin:
            newwin = True
        if newwin:
            rep, win_start = low, t
            windows.append([t, f])

    starts = [w[0] for w in windows] + [10 ** 9]
    imgdir_p = os.path.join(args.workdir, "transcripts", "img", p)
    os.makedirs(imgdir_p, exist_ok=True)
    lines = [f"# {args.title} · 第{part}讲 原始文稿（图-字幕分栏）", "",
             "| 字幕文本 | 画面 |", "| :--- | ---: |", ""]
    kept = 0
    for i, (ws, f) in enumerate(windows):
        we = starts[i + 1]
        seg = "".join(s[1] for s in subs if ws <= s[0] < we)
        if not seg and we - ws < 3:
            continue
        ts = f"{ws // 60:02d}:{ws % 60:02d}"
        url = f"https://www.bilibili.com/video/{args.bv}/?p={part}&t={ws}"
        fname = f"{ws:05d}.jpg"
        shutil.copyfile(f, os.path.join(imgdir_p, fname))
        kept += 1
        text = (seg if seg else "（此区间无字幕）").strip().replace("|", "\\|")
        lines.append(
            f"| {text} [【跳转到 {ts}】]({url}) "
            f"| <img src=\"img/{p}/{fname}\" width=\"9000\"> |"
        )
    out = os.path.join(args.workdir, "transcripts", p + ".md")
    open(out, "w", encoding="utf-8").write("\n".join(lines))
    print(f"{p}: frames={len(framefiles)} windows={len(windows)} kept={kept} -> {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--bv", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--parts", required=True)
    ap.add_argument("--diff", type=float, default=12.0)
    ap.add_argument("--minwin", type=int, default=5)
    ap.add_argument("--maxwin", type=int, default=25)
    args = ap.parse_args()
    for part in [int(x) for x in args.parts.split(",")]:
        build(part, args)


if __name__ == "__main__":
    main()
