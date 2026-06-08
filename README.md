# HN TechPulse

从 Hacker News 自动生成中文科技资讯每日简报的 Python CLI 管线。不是简单搬运 HN 热榜，而是把当天高价值讨论整理成有筛选、有判断、有社区温度的技术日报，最终输出为视频。

## 功能

- 自动获取 HN 热门故事和评论
- 文章正文抓取（Playwright + Bing 图片兜底）
- 评论情绪/质量评分 → 代表观点筛选 → LLM 判断
- LLM 生成中文简报脚本（JSON 重试、并发、segment 缓存）
- TTS 语音合成 + Remotion 视频渲染

## 快速开始

```bash
uv sync                                        # 安装依赖
cp .env.example .env                           # 配置 API keys
uv run python main.py                          # 运行完整管线
uv run python main.py --date 2026-04-26        # 指定日期
uv run python main.py --steps fetch,write_script  # 运行子链
uv run python main.py --dry-run                # 跳过 API 调用
uv run python -m pytest                        # 测试
```

## 管线步骤

```text
fetch → prefilter → fetch_comments → enrich_articles → translate_titles
  → analyze_comments → judge_comments → write_script
  → translate_comments → synthesize_audio → title
  → cover_image → cover_thumbnail → publish_guide → prepare_render → render
                                                                              ↓
                                                                          preview (opt-in)
```

`--steps X` 自动展开为 X 及之前所有步骤。每个步骤有独立缓存，可单独重跑。

## 配置

- 环境变量：`.env`（复制 `.env.example`）
- YAML 配置：[config/](config/) 目录，运行时 deep-merged

## 文档

- [开发指南 (CLAUDE.md)](CLAUDE.md) — 架构、模式、陷阱、行为准则
- [Agent 运行手册](docs/AGENT_RUNBOOK.md) — 状态文件、阻塞处理、决策门
- [项目结构](docs/PROJECT_STRUCTURE.md) — 模块地图

## 开发

```bash
uv run python scripts/quality_check.py          # 质量门禁（ruff, vulture, mypy, pytest, coverage）
uv run python scripts/quality_check.py --fix    # 自动修复
```

## License

MIT
