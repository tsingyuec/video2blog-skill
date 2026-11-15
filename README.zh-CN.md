# video2blog

[![skills.sh](https://skills.sh/b/tsingyuec/video2blog-skill)](https://skills.sh/tsingyuec/video2blog-skill)

![Platform](https://img.shields.io/badge/platform-Bilibili%20%7C%20YouTube-blue)

![Python](https://img.shields.io/badge/python-3.9%2B-blue)

![License](https://img.shields.io/badge/license-MIT-green)

[English](./README.md) | 简体中文

长视频的信息都压在几十张幻灯片上，翻页时一晃而过，事后想找回来，只能从头再看一遍。video2blog skill 将视频素材重新组织一遍：按画面变化切分视频段，一段画面配一张代表帧、一段字幕、一个跳回原片的时间戳链接，从而得到视频文字稿。博客只依据这份文稿来写，不另找材料，每一句都能对应回视频的原始字幕。幻灯片停留再久也只取一帧，一小时的讲座最后剩下两百来行。通过阅读整理好的博客即可了解视频的整体内容，同时对于重点的那部分内容，点时间戳即可跳转到对应的视频播放点。

[示例](#示例) • [安装](#安装) • [工作流程](#工作流程) • [产物](#产物) • [已知限制](#已知限制) • [项目结构](#项目结构)

## 示例

![两块并排的产出：左边是文稿，右边是由它写成的博客](examples/zh-CN/example.png)

> 左侧是文字稿，右侧是基于文字稿整理的博客

用 Stanford CS336《第 7 讲 · 并行训练》（61 分钟，源自 B 站）完整运行一次得到的产出：

| | |
| --- | --- |
| 输入 | [`bilibili.com/video/BV11LEA6eEuj/?p=7`](https://www.bilibili.com/video/BV11LEA6eEuj/?p=7) |
| 文稿 | [`examples/zh-CN/transcript.md`](examples/zh-CN/transcript.md)，185 个窗口 |
| 博客 | [`examples/zh-CN/blog.md`](examples/zh-CN/blog.md)，11 个小节 |

## 安装

```bash
npx skills add tsingyuec/video2blog-skill
```

命令会把 skill 复制到当前项目的 `.agents/skills/video2blog/`，加上 `--global` 则装到全局。它需要 Python 3.9 以上和 `requirements.txt` 里的依赖；不需要 ffmpeg，因为只下载视频流，字幕来自平台。

装好之后，把视频链接交给 agent 即可：

```
把这个视频整理成一篇博客：https://www.bilibili.com/video/BV11LEA6eEuj/?p=7
```

## 工作流程

| 步骤 | 做什么 | 产物 |
| --- | --- | --- |
| ① 下载 | yt-dlp 只取视频流，不要音频 | `videos/<id>.mp4` |
| ② 抽帧 | 每秒一张，保持原分辨率 | `frames/<id>/00012.webp` |
| ③ 字幕 | B 站走 Kedou，YouTube 走 yt-dlp | `subs/<id>.srt` |
| ④ 文稿 | 按画面变化切窗口，合并窗口内字幕，加时间戳 | `transcripts/<标题>.md` |
| ⑤ 博客 | 只依据文稿写作 | `blog/<标题>.md` |

文稿按"窗口"切分。窗口指画面保持不变的一段时间：一张幻灯片停多久，这个窗口就有多长。每个窗口对应文稿里的一行，一行配一张代表帧。

第 ② 步抽帧是每秒一张，一张幻灯片停 30 秒就有 30 张几乎相同的帧。第 ④ 步通过脚本 `scripts/build_transcript.py` 把每帧缩到 32×18 灰度，与当前窗口的代表帧比较平均绝对差：差值大于 12，且当前画面已停留至少 5 秒，才开新窗口；同一画面停留超过 25 秒，强制切分。课堂录像上能去掉约 95% 的帧，且不漏掉任何一页。这三个数是默认值，可通过参数 `--diff`、`--minwin`、`--maxwin` 调整。

文稿按窗口导出，逐窗改写通顺，再写回。改写只顺句子，不增加也不删掉信息。博客在这一步之后写，依据是改写后的文稿，不是原始字幕。

## 产物

```
<workdir>/
├─ videos/<id>.mp4                    # 仅视频流
├─ frames/<id>/00000.webp …           # 1fps，文件名即秒数
├─ subs/<id>.srt                      # 字幕；B 站另存 Kedou 原始 JSON
├─ transcripts/<标题>.md              # 文稿
├─ transcripts/img/<id>/xxxxx.webp    # 只保留代表帧
└─ blog/
   ├─ <标题>.md                       # 博客
   └─ assets/                         # 博客配图
```

帧文件以取帧的秒数命名，`00123.webp` 就是第 123 秒（00:02:03），生成时间戳链接时不需要额外的对照表。文稿和博客以视频标题命名：文件名里不能用的字符会被替换，过长的标题会截断。两者都是 Markdown，图片用相对路径引用，一份写完的文稿可以直接搬走或发布。

## 已知限制

Kedou 的请求体做了 RSA+AES 加密，脚本用标准库复现。接口一变，字幕抓取就会失效，直到加密逻辑更新；排查方法见 [`reference/kedou-api.md`](reference/kedou-api.md)。

抽帧受限于 CPU：一小时的视频要跑几分钟而不是几秒，嫌慢可降低 `--width` 或 `--fps`。

## 项目结构

```
SKILL.md                   # agent 遵循的工作流
requirements.txt
reference/
    ├─ blog-writing.md     # 写作规范：金字塔结构、SCQA、术语速查表
    └─ kedou-api.md        # Kedou 字幕接口：加密原理与排查
scripts/
    ├─ download_video.py   # yt-dlp 封装，仅视频流，支持续传
    ├─ extract_frames.py   # OpenCV 抽帧
    ├─ subtitle_fetch.py   # 字幕：B 站走 Kedou，YouTube 走 yt-dlp
    ├─ build_transcript.py # 窗口切分、去重、字幕合并、时间戳
    └─ transcript_windows.py # 改写文稿时的窗口导出与写回
examples/
    ├─ zh-CN/              # 示例产出（中文）
    │   ├─ blog.md
    │   └─ transcript.md
    └─ en/                 # 示例产出（英文）
        ├─ blog.md
        └─ transcript.md
```

## 致谢

- [yt-dlp](https://github.com/yt-dlp/yt-dlp)：视频下载
- [kedou.life](https://www.kedou.life)：在线字幕解析
- [anthropics/skills](https://github.com/anthropics/skills)：Agent Skill 规范

## License

[MIT](LICENSE)
