# video2blog-skill

[![skills.sh](https://skills.sh/b/try-agaaain/video2blog-skill)](https://skills.sh/try-agaaain/video2blog-skill)
![Platform](https://img.shields.io/badge/platform-Bilibili%20%7C%20YouTube-blue)
![License](https://img.shields.io/badge/license-MIT-green)

把视频（**B 站长课程 / 讲座**、**YouTube 视频**）整理成图文技术博客的**端到端 Agent Skill**。可作为一个 [Claude / 通用 Agent Skill](https://github.com/anthropics/skills) 使用，也可单独使用其中的脚本。

**流程概览**：下载视频 → 1fps 抽帧并按画面变化去重 → 抓取平台 AI 字幕（Kedou 接口）→ 生成 `图-字幕` 原始文稿（带可点击时间戳）→ 逐窗口通顺化改写 → 按金字塔原理写成博客。

> **核心理念**：博客必须建立在可核查的「原始文稿」之上，而不是凭空概括——每个知识点都能回跳到视频原片对应秒数。

## 特性

- 🎞️ **智能抽帧去重**：1fps 抽帧后按画面变化切分时间窗口（32×18 灰度差分），课堂幻灯片类视频去重率约 95%，50 分钟视频 2975 帧只保留约 485 张代表帧
- 📝 **可核查的原始文稿**：Markdown 分栏表格，左边幕文本、右边代表帧，每行带时间戳跳转链接（B 站 `?p=&t=` / YouTube `&t=`）
- 🌐 **多平台**：Bilibili（多 P 课程）与 YouTube（单视频）共用同一套流水线
- 🔐 **零依赖字幕抓取**：Kedou 在线字幕服务的 RSA+AES 加密协议纯标准库实现（无需 pycryptodome）
- ✍️ **内建写作规范**：金字塔原理 + SCQA 开篇 + "大一新生可懂"的术语解释（详见 `reference/blog-writing.md`）
- 🔁 **通顺化工作流**：字幕逐句拼接往往不通顺，提供「按窗口导出 → 改写 → 写回」循环工具

## 安装

```bash
pip install -r requirements.txt   # opencv-python、numpy、pillow、yt-dlp
# 无桌面环境可把 opencv-python 换成 opencv-python-headless
```

作为 Agent Skill 使用：把本仓库放入技能目录（如 Claude Code 的 `~/.claude/skills/video2blog/`），或通过 skills CLI 安装：

```bash
npx skills add try-agaaain/video2blog-skill
```

## 快速开始

以 YouTube 视频 `SYuSZIIYOfI` 为例（B 站把 `--platform youtube` 换掉、`--bv` 传 BV 号即可）：

```bash
# 1. 下载视频流（仅视频，不需要音频/ffmpeg；体积过大用 --height 720）
python scripts/download_video.py --workdir <workdir> --platform youtube --bv SYuSZIIYOfI --height 720

# 2. 1fps 抽帧
python scripts/extract_frames.py --workdir <workdir> --parts 1

# 3. 抓取 AI 字幕
python scripts/subtitle_fetch.py --platform youtube --bv SYuSZIIYOfI --out <workdir>/subs

# 4. 生成「图-字幕」原始文稿（--diff/--minwin/--maxwin 控制去重粒度）
python scripts/build_transcript.py --workdir <workdir> --platform youtube \
  --bv SYuSZIIYOfI --title "<视频标题>" --parts 1

# 5. （可选）逐窗口通顺化：导出 → 人工/AI 改写 → 写回
python scripts/transcript_windows.py dump <workdir>/transcripts/p01.md 0 600
python scripts/transcript_windows.py apply <workdir>/transcripts/p01.md << 'REWRITE'
00005|改写后的通顺文本……
REWRITE

# 6. 基于原始文稿写博客（Agent Skill 模式下由 Agent 按 SKILL.md 第 5 步完成）
```

完整参数说明、B 站多 P 下载、去重参数调优、常见故障排查见 [`SKILL.md`](SKILL.md)。

## 工作目录约定

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

## 项目结构

```
SKILL.md                      # 技能主文件：完整工作流（任务速查表 + 5 步流程）
requirements.txt              # Python 依赖清单
reference/
├─ blog-writing.md            # 金字塔原理 + 大一可懂写作规范（写博客前必读）
└─ kedou-api.md               # Kedou 字幕接口：加密原理与排查（字幕报错时读）
scripts/
├─ download_video.py          # yt-dlp 封装：仅视频流下载，支持续传
├─ extract_frames.py          # OpenCV 1fps 抽帧
├─ subtitle_fetch.py          # Kedou 字幕抓取（纯标准库，AES/RSA 内置实现）
├─ build_transcript.py        # 分栏文稿生成（窗口去重 + 字幕合并 + 时间戳）
└─ transcript_windows.py      # 文稿通顺化：窗口导出（dump）/ 写回（apply）
```

## 注意事项

- **字幕由平台 AI 生成**，可能出现识别错误（术语/人名错拼）。写博客时必须纠正，且不得编造字幕之外的事实。
- **1fps 不等于每帧都要用**：文稿/博客只保留代表帧，否则又大又冗余。
- **Kedou 限流**：连续请求约 10 次后会返回 `code:500`，脚本已内置间隔（`--delay`），大批量分批下载。
- **版权**：仅供个人学习与笔记整理，请遵守各平台的用户协议。

## 致谢

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — 视频下载
- [kedou.life](https://www.kedou.life) — 在线字幕解析服务
- [anthropics/skills](https://github.com/anthropics/skills) — Agent Skill 规范

## 免责声明

仅供个人学习与笔记整理；涉及第三方站点的接口随政策变化可能失效。

## License

[MIT](LICENSE)
