---
name: video2blog
description: "把视频（B 站长课程/讲座、YouTube 视频）整理成图文技术博客的端到端流程：下载视频、每秒抽帧并按画面变化去重、抓取平台 AI 字幕（ Kedou 接口）、生成『图片-字幕』原始文稿（带可点击时间戳）、再按金字塔写作风格写成大一新生也能看懂的博客。只要用户提到把 B 站/YouTube 视频、BV 号、视频链接整理成博客、笔记、图文稿、逐字稿、学习笔记、视频转文字、视频配图总结——即使没有明确说『博客』——也要使用本技能。"
---

# B 站/YouTube 视频 → 图文博客 工作流

**适用**：B 站视频/多 P 课程/长讲座，以及 YouTube 视频。目标产物是**每个分 P 一篇中文技术博客**（配图来自视频原片），以及一份可核查的**原始文稿**。

## 任务速查表

| 任务 | 做法 |
| --- | --- |
| 从零整理一个 BV 号 | 按第 1→5 步顺序完整走完 |
| 已下好视频/已有抽帧 | 跳到第 3 步取字幕 |
| 已有原始文稿，只要写博客 | 直接第 4 步通顺化（若未做）+ 第 5 步 |
| 字幕接口报错/限流 | 读 `reference/kedou-api.md` |
| 需要写作规范细节 | 读 `reference/blog-writing.md` |
| 抽帧/去重效果不好 | 见「参数调优速查」 |

> Bash 命令中的脚本路径均相对于本技能目录。

## 核心思路（一句话）

> **下载→抽帧→取字幕→做「图-字幕」原始文稿→写博客**。博客必须建立在「原始文稿」之上，而不是凭空概括，这样内容可核查、不遗漏。

---

## 前置依赖（都在 Python 生态内，装起来省心）

```bash
pip install -r requirements.txt   # opencv-python、numpy、pillow、yt-dlp
# 无桌面环境可把 opencv-python 换成 opencv-python-headless
```

| 工具 | 用途 |
| --- | --- |
| Python + `opencv-python` / `numpy` | 抽帧 |
| Python + `Pillow` | 图像去重、生成文稿 |
| `yt-dlp` | 下载 B 站 / YouTube 视频（仅视频流） |

## 目录约定

在工作目录（下称 `<workdir>`）下组织：

```
<workdir>/
├─ videos/        pNN.mp4                 # 下载的视频（仅视频流）
├─ frames/pNN/    00001.jpg, 00002.jpg…   # 1fps 抽帧（帧号 = 秒数+1）
├─ subs/          pNN.srt（+ kedou_NN.json）
├─ transcripts/pNN.md                     # ★ 原始文稿（图-字幕对照）
├─ transcripts/img/pNN/xxxxx.jpg          # 稿中保留的代表帧
└─ blog/
   ├─ blNN.md                             # ★ 每个分 P 一篇博客
   └─ assets/pNN/                         # 博客配图
```

---

## 第 1 步：获取信息并下载（仅视频流）

统一用 `scripts/download_video.py`（yt-dlp 封装）：只下视频流不要音频（字幕来自在线服务，无需 ffmpeg 合并）、优先 avc1/H.264（OpenCV 解码最稳）、支持断点续传。

```bash
# B 站（多 P，--parts 圈定范围）
python scripts/download_video.py --workdir "<workdir>" --bv <BV> --parts 1,2,3

# YouTube（单视频；分辨率过高/体积过大时用 --height 720）
python scripts/download_video.py --workdir "<workdir>" --platform youtube --bv <视频ID> --height 720

# 查看分 P 信息（标题 / 时长），决定 --parts 范围
python -m yt_dlp --no-warnings --skip-download \
  --print "%(playlist_index)s|%(duration)s|%(title)s" "https://www.bilibili.com/video/<BV>/"
```

要点：
- 字幕来自在线服务，**不需要音频**，所以只下视频流即可，避免音视频合并且不需要 ffmpeg。
- 优先 `avc1`(H.264) 是为了让 OpenCV 解码更稳；若某些视频只有 AV1/HEVC，OpenCV 一般也能解。
- **单 P 下载时 `%(playlist_index)s` 会变成 `NA`**，所以要么整季一起下（`-I`），要么改用固定文件名（download_video.py 已处理）。
- **续传**：yt-dlp 默认从 `.part` 断点续传，但**换了格式（如改 --height）旧 .part 会失效**（HTTP 416），需先删 `videos/*.part`。
- 多 P 视频可能含「中配版 / 原版」等重复分 P，先看标题确认唯一讲次再决定下载范围。

## 第 2 步：按 1fps 抽帧（OpenCV）

```bash
python scripts/extract_frames.py --workdir "<workdir>" --parts 1,2,3
```

- 帧号 = 秒数 + 1（`00001.jpg` 对应第 0 秒），与第 4 步的时间对齐。
- 默认缩放到宽 960、JPEG 质量 85；可用 `--width 0` 保留原始尺寸。
- 速度取决于 CPU 解码，长视频会慢一些；`--force` 可强制重跑。

## 第 3 步：抓取字幕（在线服务 Kedou）

平台 AI 字幕采用在线字幕服务 **kedou.life** 的接口（支持 B 站与 YouTube）；它对 body 做了 RSA+AES 加密，`scripts/subtitle_fetch.py` 已实现（纯 Python 标准库，零依赖），直接跑：

```bash
# B 站（多 P）
python scripts/subtitle_fetch.py --out "<workdir>/subs" --bv <BV> --parts 1,2,3

# YouTube（单视频，忽略 --parts）
python scripts/subtitle_fetch.py --platform youtube \
  --bv <视频ID> --out "<workdir>/subs"
```

- B 站每个分 P 输出 `subs/kedou_NN.json`；YouTube 输出 `subs/kedou_<视频ID>.json`。其中 `data.subtitleItemVoList[0].content` 即 SRT 文本。
- **限流**：连续请求约 10 次后返回 `code:500 请求过于频繁`。脚本默认每次间隔数秒并逐条容错；**大批量时分批、被限流后等 1–2 分钟再续**。
- 若站点改版/失效（报加密错误、空字幕等），读 `reference/kedou-api.md` 了解加密原理与排查。

## 第 4 步：生成「图-字幕」原始文稿（去重 + 合并 + 时间戳）

本流程的核心工件。虽然抽了 1fps，但**绝大多数相邻帧几乎一样**（同一张幻灯片停留几十秒）。做法：按**画面变化**切分时间窗口，每个窗口只保留一张代表帧，并把窗口内字幕合并。

```bash
# B 站（多 P）
python scripts/build_transcript.py --workdir "<workdir>" --bv <BV> \
  --title "<视频标题>" --parts 1,2,3 --diff 12 --minwin 5 --maxwin 25

# YouTube（--bv 传 11 位视频 ID，跳转链接自动生成为 youtu.be 格式的 t=秒）
python scripts/build_transcript.py --workdir "<workdir>" --platform youtube \
  --bv <视频ID> --title "<视频标题>" --parts 1
```

- 脚本会先把字幕 json（B 站 `kedou_NN.json` / YouTube `kedou_<视频ID>.json`）导出为 `subs/pNN.srt`，再生成 `transcripts/pNN.md`。时间戳跳转链接按平台自动生成：B 站 `?p=N&t=秒`，YouTube `&t=秒`。
- **判据**：帧缩到 32×18 灰度做平均绝对差；与当前窗口代表帧差异 `> --diff` 且距窗口起点 `≥ --minwin` 秒 → 开新窗口；同画面最长停留 `--maxwin` 秒强制切一刀。
- **参数经验**：`--diff 12 --minwin 5 --maxwin 25` 对课堂幻灯片约 95% 去重率。画面切换剧烈就调大 `--diff`，想更细就调小。
- 输出为 MD 表格分栏格式（左字右图），每行一个窗口，形如：

```markdown
| 字幕文本 | 画面 |
| :--- | ---: |
| 该时间窗口内所有字幕合并后的文本…… [【跳转到 12:34】](https://www.bilibili.com/video/<BV>/?p=3&t=754) | <img src="img/p03/00754.jpg" width="9000"> |
```

  无字幕窗口左栏写「（此区间无字幕）」；右栏内联 `<img width="9000">`（MD 表格无法指定列宽，用图片 width 撑大右栏，链接保持可点）。

**通顺化（不可跳过）**：合并出的窗口文本是字幕逐句拼接，往往不通顺（错拼、断句错位、口语碎片）。写博客前先逐窗口改写（可润色、合并断句、纠正错拼），但**不得丢信息**，只改左栏字幕文本。用 `scripts/` 里的两个工具做"导出→改写→写回"循环：

```bash
# 导出某区间窗口：输出每行形如 01202|窗口文本
python scripts/transcript_windows.py dump transcripts/p08.md 1202 1700

# 把改写后的 NNNNN|新文本 用 heredoc 写回（⚠️ heredoc 必须写结束分隔符）
python scripts/transcript_windows.py apply transcripts/p08.md << 'REWRITE'
01202|改写后的文本……
01222|改写后的文本……
REWRITE
```

- 每批 30–60 个窗口，导出一段、改写一段、写回一段。
- Windows + Git Bash 终端默认 GBK：打印中文的 Python 命令要加 `PYTHONIOENCODING=utf-8`。
- ⚠️ 通顺化后**不要重跑**本脚本——它会覆盖已改写的文稿。
- 常见 ASR 错拼在改写时顺手替换（清单见 `reference/blog-writing.md`）。

## 第 5 步：写博客（金字塔原理 + 大一可懂）

对每个分 P，**基于第 4 步的原始文稿**写 `blog/blNN.md`。完整写作规范见 `reference/blog-writing.md`，要点：

要点：金字塔写作风格（结论先行、SCQA 开篇、MECE 分组、3–5 个要点一组、标题写判断句）与章节式结构、配图/时间戳、完整覆盖等全部细则，见 `reference/blog-writing.md`（写博客前必读）。

> 长文任务建议：让子任务「**分段读取文稿、边写边追加**」，避免单次动作过大导致中断。

## 参数调优速查

| 现象 | 调整 |
| --- | --- |
| 保留帧太多、内容重复 | 调大 `--diff`（如 14–16）、调大 `--minwin` |
| 保留帧太少、漏掉幻灯片 | 调小 `--diff`（如 8–10）、调大 `--maxwin` |
| 字幕请求被限流 | 分批下载，间隔 1–2 分钟重试 |
| 抽帧太慢 | 降低 `--width`（如 640）或增大抽帧间隔（`--fps 0.5`） |
| 子任务中断 | 分段读写、多次追加；或按讲次拆分并行 |

## 注意事项

- **字幕是 B 站 AI 生成**，可能出现识别错误（`CS336`→`cs three three nox`、人名/术语错拼）。写博客时必须纠正，且不得编造字幕之外的事实。
- **1fps 不等于每帧都要用**：文稿/博客只保留代表帧，否则又大又冗余。
- **版权**：仅用于个人学习与笔记整理。

## 配套文件

- `scripts/extract_frames.py` — 1fps 抽帧（OpenCV）
- `scripts/subtitle_fetch.py` — Kedou 字幕抓取
- `scripts/build_transcript.py` — 图-字幕原始文稿生成
- `scripts/transcript_windows.py` — 文稿通顺化的"按窗口导出（dump）/写回（apply）"工具
- `reference/kedou-api.md` — 字幕接口加密原理与维护（第 3 步报错时读）
- `reference/blog-writing.md` — 金字塔原理 + 写作规范（写博客前必读）
- `requirements.txt` — Python 依赖清单
