# video2blog

[![skills.sh](https://skills.sh/b/tsingyuec/video2blog-skill)](https://skills.sh/tsingyuec/video2blog-skill)
![Platform](https://img.shields.io/badge/platform-Bilibili%20%7C%20YouTube-blue)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

English | [简体中文](./README.zh-CN.md)

A long video keeps its information concentrated on a few dozen slides, each of which flips past in a moment; to find a particular point afterwards, you have to watch from the start. video2blog reorganises the material: it cuts the video where the picture changes, and gives each segment one representative frame, the captions spoken over it and a timestamp link back to the video, which together form the video transcript. The post is written from that transcript alone and consults no other material, so every sentence rests on the video's original captions. A slide that lingers still yields a single frame, and an hour-long lecture ends up at about two hundred lines. Reading the finished post is enough to grasp the video as a whole, and for the parts that matter, the timestamp jumps to the corresponding point in the playback.

It can also start from a keyword: the skill searches for candidates, ranks them by their captions, and shortlists one to three videos worth writing about, each becoming its own post. Captions fetched for that ranking are reused by the download-and-write steps.

[Example](#example) • [Install](#install) • [How it works](#how-it-works) • [Output](#output) • [Limitations](#limitations) • [Repo structure](#repo-structure)

## Example

![Split view: the transcript on the left, the blog written from it on the right](examples/en/example.png)

> The transcript is on the left; the blog written from it is on the right.

One run on Stanford CS336 *Lecture 7, Parallel training* (61 minutes, on Bilibili):

| | |
| --- | --- |
| Input | [`bilibili.com/video/BV11LEA6eEuj/?p=7`](https://www.bilibili.com/video/BV11LEA6eEuj/?p=7) |
| Transcript | [`examples/en/transcript.md`](examples/en/transcript.md), 185 windows |
| Blog | [`examples/en/blog.md`](examples/en/blog.md), 11 sections |

## Install

```bash
npx skills add tsingyuec/video2blog-skill
```

The CLI copies the skill into `.agents/skills/video2blog/` for the current project, or into your global skills directory with `--global`. It needs Python 3.9 or newer and the packages in `requirements.txt`; ffmpeg is not needed, because only the video stream is downloaded and the captions come from the platform. The blog checks are Python 3; they do not need Node.js or KaTeX.

Once installed, hand the agent a link:

```
Turn this video into a blog post: https://www.bilibili.com/video/BV11LEA6eEuj/?p=7
```

Or just give it a keyword:

```
Find the videos worth watching on this topic: KV cache quantization
```

## How it works

| Step | What happens | Output |
| --- | --- | --- |
| ① find | given a keyword, search both platforms and rank candidates by their captions | shortlist; captions cached for reuse |
| ② download | yt-dlp fetches the video stream, audio excluded | `videos/<id>.mp4` |
| ③ frames | one frame per second, kept at full size | `frames/<id>/00012.webp` |
| ④ captions | Kedou on Bilibili, yt-dlp on YouTube | `subs/<id>.srt` |
| ⑤ transcript | windows cut on picture changes, captions merged, timestamps added | `transcripts/<title>.md` |
| ⑥ blog | written from the transcript only | `blog/<title>.md` |
| ⑦ check | image references, timestamps, project build | a clean post and its assets |

Start at ② when you already have a link; start at ① when you only have a keyword. Captions fetched for ① are reused by ④, not requested twice.

Each post carries at least 10 timestamps, increasing with the video's length. A video close to 60 minutes may be split into two posts when its content has two independent centres; the file names take `-1` / `-2` suffixes.

A window is a stretch of the video in which the picture does not change: one slide, however long it stays up, is one window. Each window becomes one row of the transcript, with one representative frame.

Step ③ extracts one frame per second, so a slide that stays up for 30 seconds produces 30 near-identical frames. Step ⑤ has `scripts/pipeline/build_transcript.py` reduce each frame to 32×18 grayscale and compare it with the current window's representative frame: a new window opens when the mean difference exceeds 12 and the current picture has been on screen for at least 5 seconds, while a single picture is cut off at 25 seconds. On lecture videos that drops about 95% of the frames without losing a slide. The three numbers are defaults, adjustable with `--diff`, `--minwin` and `--maxwin`.

The transcript is dumped window by window, rewritten for readability, and written back. The rewrite only smooths sentences; it may not add or remove information. The blog is written from the corrected transcript, not from the raw captions.

## Output

```
<workdir>/
├─ videos/<id>.mp4                    # video stream only
├─ frames/<id>/00000.webp …           # 1 fps, filename is the second
├─ subs/<id>.srt                      # captions; Bilibili also keeps Kedou's JSON
├─ transcripts/<title>.md             # the transcript
├─ transcripts/img/<id>/xxxxx.webp    # representative frames only
└─ blog/
   ├─ <title>.md                      # the blog
   └─ assets/                         # blog images
```

Frames are named by the second they were taken from, so `00123.webp` is the frame at 00:02:03 and the timestamp links need no lookup table. Transcripts and posts take their names from the video title; characters a file name cannot hold are replaced and long titles are cut short. Both are plain Markdown with relative image paths, so a finished transcript can be moved or published unchanged.

## Limitations

Kedou's request body is RSA+AES encrypted and the scripts reproduce that encryption with the standard library. If the API changes, caption fetching stops working until the encryption is updated; see [`reference/kedou-api.md`](reference/kedou-api.md) for the debugging notes.

Frame extraction is CPU-bound, so an hour of video takes minutes rather than seconds. Lower `--width` or `--fps` to speed it up.

## Repo structure

```
SKILL.md                   # the workflow the agent follows
requirements.txt
reference/
    ├─ blog-writing.md     # writing style, images, timestamps, layout
    └─ kedou-api.md        # Kedou caption API: encryption and troubleshooting
scripts/
    ├─ README.md           # script entry points
    ├─ pipeline/           # download, frames, captions, transcript, rewrite
    │   ├─ download_video.py
    │   ├─ extract_frames.py
    │   ├─ subtitle_fetch.py
    │   ├─ build_transcript.py
    │   └─ transcript_windows.py
    └─ check/              # blog checks
        ├─ check_images.py
        └─ check_blog.py
examples/
    ├─ zh-CN/              # example output, Chinese
    │   ├─ blog.md
    │   └─ transcript.md
    └─ en/                 # example output, English
        ├─ blog.md
        └─ transcript.md
```

## Acknowledgements

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) for video download
- [kedou.life](https://www.kedou.life) for online caption extraction
- [anthropics/skills](https://github.com/anthropics/skills) for the Agent Skills standard

## License

[MIT](LICENSE)
