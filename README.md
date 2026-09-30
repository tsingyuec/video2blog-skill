# bilibili-blog

把 B 站视频（长课程 / 讲座）整理成图文技术博客的**端到端工作流**（作为 Claude/通用 Agent 的 Skill 使用）。

**流程概览**：下载视频（仅视频流，无需 ffmpeg）→ 1fps 抽帧并按画面变化去重 → 在线抓取 B 站 AI 字幕（Kedou 接口，纯 Python 加密实现）→ 生成「左右分栏」图-字幕原始文稿（MD 表格，左字幕右大图，时间戳可点击）→ 逐窗口通顺化改写 → 按金字塔原理（SCQA + 章节式）写博客。

完整使用说明见 [`SKILL.md`](SKILL.md)。

## 目录结构

```
SKILL.md                  # 技能主文件：完整工作流
reference/blog-writing.md # 金字塔原理 + 大一可懂写作规范
reference/kedou-api.md    # Kedou 字幕接口：加密原理与排查
scripts/
├─ extract_frames.py       # OpenCV 1fps 抽帧
├─ kedou_fetch.py          # Kedou 字幕抓取（纯标准库，AES/RSA 内置实现）
├─ build_transcript.py     # 分栏文稿生成（窗口去重 + 字幕合并 + 时间戳）
├─ dump_windows.py         # 文稿通顺化：按窗口导出
└─ apply_windows.py        # 文稿通顺化：按窗口写回
```

## 特点

- **零 Node、零 ffmpeg**：全流程纯 Python（抽帧用 OpenCV）；字幕加密为纯标准库实现（已通过 NIST AES 测试向量）。
- **可核查**：博客建立在逐行可回溯的原始文稿上，关键结论均带可点击的 B 站时间戳链接。
- **分栏文稿**：`| 字幕文本（含时间戳） | <img width="9000"> |`，在任意 Markdown 预览器里即得左字右图阅读版。

## 免责声明

仅供个人学习与笔记整理；涉及第三方站点的接口随政策变化可能失效。
