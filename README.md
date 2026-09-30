# video2blog-skill

[![skills.sh](https://skills.sh/b/tsingyuec/video2blog-skill)](https://skills.sh/tsingyuec/video2blog-skill)
![Platform](https://img.shields.io/badge/platform-Bilibili%20%7C%20YouTube-blue)
![License](https://img.shields.io/badge/license-MIT-green)

把视频（**Bilibili / YouTube 视频**）整理成图文技术博客的**端到端 Agent Skill**。可作为 [Claude / 通用 Agent Skill](https://github.com/anthropics/skills) 使用，也可单独使用其中的脚本。

**流程概览**：下载视频 → 1fps 抽帧并按画面变化去重 → 抓取平台 AI 字幕（Kedou 接口）→ 生成 `图-字幕` 原始文稿（带可点击时间戳）→ 逐窗口通顺化改写 → 按金字塔写作风格写成博客。

> **核心理念**：博客必须建立在可核查的「原始文稿」之上，而不是凭空概括——每个知识点都能回跳到视频原片对应秒数。

## 特性

- 🎞️ **智能抽帧去重**：1fps 抽帧后按画面变化切分时间窗口（32×18 灰度差分）去重以避免重复画面
- 📝 **可核查的原始文稿**：Markdown 分栏表格，左边幕文本、右边代表帧，每行带时间戳跳转链接
- 🌐 **多平台**：Bilibili 与 YouTube 共用同一套单视频流水线；多个视频重复执行即可
- 🔐 **零依赖字幕抓取**：Kedou 在线字幕服务的 RSA+AES 加密协议纯标准库实现（无需 pycryptodome）
- ✍️ **内建写作规范**：金字塔写作风格 + SCQA 开篇 + "初学者可读"的术语解释（详见 `reference/blog-writing.md`）
- 🔁 **通顺化工作流**：字幕逐句拼接往往不通顺，提供「按窗口导出 → 改写 → 写回」循环工具

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

完整示例见 [`examples/`](examples/)——由本 skill 对视频《[电脑显卡GPU的工作原理，它是如何工作的？和CPU有什么区别？](https://www.bilibili.com/video/BV12FJtzRE6W/)》完整跑一遍得到：

- [`blog.md`](examples/blog.md)：最终博客（金字塔结构 + 术语速查表 + 时间戳回链）
- [`transcript.md`](examples/transcript.md)：第 4 步的原始文稿（图-字幕分栏，每行可回跳视频）

> 示例配图托管在同仓库的 `media` 分支（`--depth 1` 安装不会下载），画面帧截取自上述 B 站视频，仅用于演示本 skill 的输出效果。

## 产物目录约定

```
<workdir>/
├─ videos/        video1.mp4                 # 下载的视频（仅视频流）
├─ frames/video1/    00000.jpg, 00001.jpg…   # 1fps 抽帧（编号 = 秒数）
├─ subs/          video1.srt（+ kedou_<视频ID>.json）
├─ transcripts/video1.md                     # ★ 原始文稿（图-字幕对照）
├─ transcripts/img/video1/xxxxx.jpg          # 稿中保留的代表帧
└─ blog/
   ├─ blog.md                             # ★ 本视频的博客
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
    ├─ subtitle_fetch.py          # Kedou 字幕抓取（纯标准库，AES/RSA 内置实现）
    ├─ build_transcript.py        # 分栏文稿生成（窗口去重 + 字幕合并 + 时间戳）
    └─ transcript_windows.py      # 文稿通顺化：窗口导出（dump）/ 写回（apply）
examples/
    ├─ README.md                  # 示例说明（blog.md + transcript.md；配图在 media 分支）
    ├─ blog.md                    # 完整示例产出：最终博客
    └─ transcript.md              # 完整示例产出：图-字幕原始文稿
```

## 致谢

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — 视频下载
- [kedou.life](https://www.kedou.life) — 在线字幕解析服务
- [anthropics/skills](https://github.com/anthropics/skills) — Agent Skill 规范

## License

[MIT](LICENSE)
