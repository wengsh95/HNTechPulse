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
fetch → prefilter → fetch_comments → enrich_articles → translate_titles
  → analyze_comments → judge_comments → write_script → review_script
  → human_review → translate_comments → prepare_subtitles → synthesize_audio
  → title → cover_image → cover_thumbnail → draft_storyboard → apply_storyboard
  → publish_guide → prepare_render → render
```

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
