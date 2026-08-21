# HN TechPulse

从 Hacker News 自动生成科技解说视频的 Python CLI 管线。

## 功能

- 自动获取 HN 热门故事和评论
- 文章正文抓取（Playwright + Bing 图片兜底）
- 评论情绪/质量评分 → 代表观点筛选 → LLM 判断
- LLM 生成结构化解说脚本（含人工审核门）
- TTS 配音 + Remotion/HyperFrames 视频渲染，产出 MP4

## 快速开始

```bash
uv sync                                        # 安装依赖
cp .env.example .env                           # 配置 API keys
uv run python main.py                          # 运行完整管线
uv run python main.py --date 2026-04-26        # 指定日期
uv run python scripts/agent_run.py --date 2026-04-26  # 托管运行（preflight + 状态检查 + 审计）
uv run python main.py --dry-run                # 跳过 API 调用
uv run python -m pytest                        # 测试
```

## 管线步骤

```text
fetch → prefilter → fetch_comments → enrich_articles → judge_comments
  → write_script → draft_quick_news → prepare_story_images
  → title → cover_image
  → cover_thumbnail → draft_storyboard → human_review → apply_storyboard
  → prepare_subtitles → synthesize_audio → prepare_render → render
```

标题调用会同时生成三种封面文案和图像提示词并写入 `publish/title.json`，封面阶段复用
缓存，只负责调用图像生成器。开场白直接从已选故事钩子拼接，不再单独调用一次 LLM。
速览阶段会顺带写入确定性的 `video_structure.json`，不再单独暴露结构整理步骤。
速览阶段完成结构定型后会立即翻译最终精选评论，评论翻译不再单独占用一个默认状态；
评论翻译由速览阶段内部完成，不再作为可调度步骤暴露。
最终 `prepare_render` 阶段会顺带生成发布指南，默认链不再单独占用一个发布状态；
发布指南由渲染准备阶段内部完成，不再作为可调度步骤暴露。
脚本、音频与渲染产物分别缓存；可按步骤单独重跑下游阶段。

## 配置

- 环境变量：`.env`（复制 `.env.example`）
- YAML 配置：[config/](config/) 目录，运行时 deep-merged

## 文档

- [Agent 运行手册](docs/AGENT_RUNBOOK.md) — 状态文件、阻塞处理、决策门
- [项目结构](docs/PROJECT_STRUCTURE.md) — 模块地图

## 开发

```bash
uv run python scripts/quality_check.py          # 质量门禁（ruff, vulture, mypy, pytest, coverage）
uv run python scripts/quality_check.py --fix    # 自动修复
```

## License

MIT
