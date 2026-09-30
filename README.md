# video2blog

把 B 站视频（长课程 / 讲座）整理成图文技术博客的**端到端工作流**（作为 Claude/通用 Agent 的 Skill 使用）。

**流程概览**：下载视频 → 1fps 抽帧并按画面变化去重 → 在线抓取 B 站 AI 字幕（Kedou 接口）→ 生成 `图-字幕` 原始文稿→ 逐窗口通顺化改写 → 整理为博客。

完整使用说明见 [`SKILL.md`](SKILL.md)。

## 安装

```bash
pip install -r requirements.txt
```

## 目录结构

```
SKILL.md                      # 技能主文件：完整工作流（action 速查表 + 5 步流程）
requirements.txt              # Python 依赖清单
reference/
├─ blog-writing.md            # 金字塔原理 + 大一可懂写作规范（写博客前必读）
└─ kedou-api.md               # Kedou 字幕接口：加密原理与排查（字幕报错时读）
scripts/
├─ extract_frames.py          # OpenCV 1fps 抽帧
├─ subtitle_fetch.py          # Kedou 字幕抓取（纯标准库，AES/RSA 内置实现）
├─ build_transcript.py        # 分栏文稿生成（窗口去重 + 字幕合并 + 时间戳）
├─ transcript_windows.py      # 文稿通顺化：窗口导出（dump）/ 写回（apply）
```


## 免责声明

仅供个人学习与笔记整理；涉及第三方站点的接口随政策变化可能失效。
