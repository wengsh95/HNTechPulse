# HN TechPulse

从 Hacker News 自动生成小红书科技深度卡片的 Python CLI 管线。不是简单搬运 HN 热榜，而是选出一条高张力新闻，整理成有事实、有社区分歧的 6 页图文。

## 功能

- 自动获取 HN 热门故事和评论
- 文章正文抓取（Playwright + Bing 图片兜底）
- 评论情绪/质量评分 → 代表观点筛选 → LLM 判断
- LLM 选择单条焦点新闻并生成结构化 6 页卡片契约
- Guizang Swiss 模板 + Playwright 渲染 1080×1440 PNG 和总览图

## 快速开始

```bash
uv sync                                        # 安装依赖
cp .env.example .env                           # 配置 API keys
uv run python main.py                          # 运行完整管线
uv run python main.py --date 2026-04-26        # 指定日期
uv run python main.py --steps render_xhs_cards    # 只重新渲染现有卡片
uv run python main.py --dry-run                # 跳过 API 调用
uv run python -m pytest                        # 测试
```

## 管线步骤

```text
fetch → prefilter → fetch_comments → enrich_articles → translate_titles
  → analyze_comments → judge_comments → plan_xhs_cards → render_xhs_cards
```

卡片规划与 PNG 渲染分别缓存；只改模板时可单独运行 `render_xhs_cards`。

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
