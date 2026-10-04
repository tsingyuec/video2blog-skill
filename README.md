# video2blog-skill

[![skills.sh](https://skills.sh/b/tsingyuec/video2blog-skill)](https://skills.sh/tsingyuec/video2blog-skill)
![Platform](https://img.shields.io/badge/platform-Bilibili%20%7C%20YouTube-blue)
![License](https://img.shields.io/badge/license-MIT-green)

把视频（**Bilibili / YouTube 视频**）整理成图文技术博客的**端到端 Agent Skill**。可作为 [Claude / 通用 Agent Skill](https://github.com/anthropics/skills) 使用，也可单独使用其中的脚本。

> **核心理念**：博客必须建立在可核查的「原始文稿」之上，而不是凭空概括——每个知识点都能回跳到视频原片对应秒数。

## 处理流程

- 输入：视频链接（Bilibili / YouTube）
- ① 下载视频（yt-dlp）
- ② 每秒抽取一张视频帧，并按画面变化去重，得到关键帧
- ③ 抓取平台 AI 字幕（Kedou），并根据关键帧划分窗口，合并窗口内的字幕
- ④ 逐窗口改写文稿使其字幕通顺，得到「图-字幕」文稿，附带时间戳可跳转到视频对应位置
- ⑤ 基于文稿整理得到结构清晰的博客

## 特性

- **自动化流程**：输入视频链接后，下载、抽帧、抓字幕、生成图文文稿、写博客依次完成，长视频无需从头观看。
- **内容可回溯**：博客基于视频原始字幕与幻灯片撰写，正文时间戳可跳回原片对应位置进行回看。
- **金字塔写作**：结论先行、SCQA 开篇，术语首次出现时解释，标题写成观点句。
- **关键帧去重**：同一画面无论停留多久只保留一张代表帧，文稿中不会堆叠重复截图。
- **多平台支持**：B 站与 YouTube 通用；字幕直接读取平台 AI 字幕，抓取逻辑用标准库实现，无第三方依赖。

## 手动安装

```bash
pip install -r requirements.txt   # opencv-python、numpy、pillow、yt-dlp
# 无桌面环境可把 opencv-python 换成 opencv-python-headless
```

作为 Agent Skill 使用可通过 skills CLI 安装（自动将本仓库放入技能目录 `~/.agent/skills/video2blog/`）：

```bash
npx skills add tsingyuec/video2blog-skill
```

## 由你的Agent安装

```
Use the skills in "https://github.com/tsingyuec/video2blog-skill" that are relevant to the current task. Run `npx skills add "https://github.com/tsingyuec/video2blog-skill"` and select the relevant skills, then follow their instructions.
```

## 示例输出

采用本 skill 对《[Stanford CS336 第 7 讲 · 并行训练](https://www.bilibili.com/video/BV11LEA6eEuj/?p=7)》完整跑一遍得到：

![示例：图-字幕原始文稿（左字幕、右代表帧，可点击时间戳）](https://raw.githubusercontent.com/tsingyuec/video2blog-skill/media/docs/example.png)

- [`blog.md`](examples/blog.md)：最终博客（金字塔结构 + 术语速查表 + 时间戳回链）
- [`transcript.md`](examples/transcript.md)：第 4 步的原始文稿（图-字幕分栏，每行可回跳视频）

> 示例配图托管在同仓库的 `media` 分支（`--depth 1` 安装不会下载），画面帧截取自上述 B 站视频，仅用于演示本 skill 的输出效果。

## 产物目录约定

```
<workdir>/
├─ videos/        video1.mp4                 # 下载的视频（仅视频流）
├─ frames/video1/    00000.webp, 00001.webp… # 1fps 抽帧（默认 WebP；编号 = 秒数）
├─ subs/          video1.srt（+ B 站原始响应 kedou_<视频ID>.json）
├─ transcripts/<视频标题>.md                 # ★ 原始文稿（图-字幕对照）
├─ transcripts/img/video1/xxxxx.webp         # 稿中保留的代表帧
└─ blog/
   ├─ <视频标题>.md                        # ★ 本视频的博客
   └─ assets/                             # 博客配图
```

## 项目结构

```
SKILL.md                      # 技能主文件：完整工作流（任务速查表 + 5 步流程）
requirements.txt              # Python 依赖清单
reference/
    ├─ blog-writing.md            # 金字塔写作风格 + 初学者可读写作规范（写博客前必读）
    └─ kedou-api.md               # Kedou 字幕接口：加密原理与排查（字幕报错时读）
scripts/
    ├─ download_video.py          # yt-dlp 封装：仅视频流下载，支持续传
    ├─ extract_frames.py          # OpenCV 1fps 抽帧
    ├─ subtitle_fetch.py          # 字幕抓取（B 站走 Kedou，YouTube 走 yt-dlp）
    ├─ build_transcript.py        # 分栏文稿生成（窗口去重 + 字幕合并 + 时间戳）
    └─ transcript_windows.py      # 文稿通顺化：窗口导出（dump）/ 写回（apply）
examples/
    ├─ blog.md                    # 完整示例产出：最终博客
    └─ transcript.md              # 完整示例产出：图-字幕原始文稿
```

## 致谢

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — 视频下载
- [kedou.life](https://www.kedou.life) — 在线字幕解析服务
- [anthropics/skills](https://github.com/anthropics/skills) — Agent Skill 规范

## License

[MIT](LICENSE)
