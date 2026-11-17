# scripts/ — 流水线与检查

只放可执行脚本。素材、产物与写作规范不在这里。

## `pipeline/` — 视频 → 图文稿

| 脚本 | 作用 |
| --- | --- |
| `download_video.py` | yt-dlp 封装，仅下载视频流，支持断点续传 |
| `extract_frames.py` | 1fps 抽帧（OpenCV），文件名即秒数 |
| `subtitle_fetch.py` | 字幕：B 站走 Kedou，YouTube 走 yt-dlp（支持 `--cookies`） |
| `build_transcript.py` | 按画面变化切窗口、去重、合并窗口字幕、加时间戳 |
| `transcript_windows.py` | 文稿通顺化的「按窗口导出 / 写回」工具 |

命令与参数见 `SKILL.md` 第 2–5 步；脚本均以 `--workdir` 指定工作目录。

## `check/` — 博客检查

| 脚本 | 检查什么 | 依赖 |
| --- | --- | --- |
| `check_images.py` | 图片引用是否存在、是否普通文件/0 字节、扩展名与文件头是否一致、是否在发布白名单、目录内孤儿图 | Python 3 |
| `check_blog.py` | 时间戳数量与 `t` 一致性、标题层级、`<img>`/width 写法 | Python 3 |
| `convert_math_inline.py` | 把代码样式公式批量转成 `$...$` 的迁移工具（按需） | Python 3 |

```bash
python3 scripts/check/check_images.py <博客文件或目录>
python3 scripts/check/check_blog.py <博客文件或目录>
```

公式渲染检查与构建检查由具体项目维护，不在本 skill 内。脚本的退出码：0 通过，1 有问题，2 用法错误。

**以脚本输出为准**：报告里的缺失、格式、孤儿图、时间戳问题都要修到 0；不要改脚本或忽略输出。
