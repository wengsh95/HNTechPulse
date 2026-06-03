# HN TechPulse

从 Hacker News 自动生成中文科技资讯每日简报的 Python 应用。项目目标不是简单搬运 HN 热榜，而是把当天高价值讨论整理成有筛选、有判断、有社区温度的技术日报。

## 功能特点

- 自动获取 Hacker News 热门故事和评论。
- 文章 enrich：抓取正文、图片、截图，并支持 Playwright 和 Bing 图片兜底。
- 评论分析与代表观点筛选：情绪、质量评分、引用惩罚、稳定翻译 key。
- LLM 生成中文简报脚本，支持 JSON 重试、截断后扩展 token 上限、并发 story 生成和 segment 缓存版本控制。
- Remotion 视频渲染输出，细粒度缓存支持断点续跑。

## 当前重点

已完成的主要体验升级：

- 评论管线重构：CommentAnalyzer 评分 → CommentJudge 预筛 → LLM 判断 → 脚本消费 `quote_candidates`，下游不再独立重选。
- 管线模块拆分：content_io、timing_engine、tts_processor、transcript_generator、report_generator、script_io。
- ~~Streamlit 编辑界面：可通过 `--steps editor` 手动调整脚本。~~（2026-06-03 移除：见 ROADMAP M5）

下一步优先事项：标准版时长控制、标准版/完整版结构、图片质量护栏。

## 安装

```bash
uv sync
```

### Windows 终端编码

如果在 PowerShell 里看到中文注释、日志或脚本内容变成乱码，先在项目根目录运行：

```powershell
. .\scripts\encoding.ps1
```

这个脚本会把当前 PowerShell 会话切到 UTF-8，并设置 Python 的标准输入/输出编码。项目文件本身按 UTF-8 保存，`.editorconfig` 和 `.gitattributes` 会帮助编辑器和 Git 保持一致。

## 配置

1. 复制环境变量示例：
```bash
cp .env.example .env
```

2. 编辑 `.env` 添加 API keys：
```env
OPENAI_API_KEY=your_api_key_here
```

3. 根据需要修改 [config/](config/) 目录中的 YAML 配置文件（LLM 模型、视频参数等，deep-merged）

## 使用

### 完整流程

```bash
uv run python main.py
```

### 指定日期

```bash
uv run python main.py --date 2026-04-26
```

### 运行特定步骤

```bash
# 只获取内容和生成脚本
uv run python main.py --steps fetch,script

# 只运行翻译/TTS 和渲染
uv run python main.py --steps produce,render
```

可用步骤：

```text
fetch -> enrich -> script -> produce -> render
```

### 其他选项

```bash
# 调试模式
uv run python main.py --debug

# 试运行（跳过 API 调用）
uv run python main.py --dry-run
```

## 项目结构

```
hn-techpulse/
├── src/
│   ├── core/           # 核心接口和数据模型
│   ├── providers/      # Fetcher/Enricher/LLM/Renderer 等服务提供者
│   ├── pipeline/       # 流程编排、评论分析、翻译、脚本生成、TTS、报告
│   ├── editor/         # ~~Streamlit 脚本编辑界面~~（2026-06-03 起为 orphan 代码）
│   └── utils/          # 工具模块
├── prompts/            # LLM 提示词模板
├── tests/              # 单元测试
├── scripts/            # 质量检查脚本
├── data/               # 输出数据目录
├── config/             # YAML 配置文件（deep-merged）
└── main.py             # 入口文件
```

## 测试

```bash
# 运行所有测试
uv run python -m pytest

# 运行特定测试文件
uv run python -m pytest tests/test_pipeline.py

# 运行最近重点覆盖的测试
uv run python -m pytest tests/test_article_enricher.py
```

## 代码质量

```bash
# Python 质量门禁（一站式）
uv run python scripts/quality_check.py              # 运行所有检查
uv run python scripts/quality_check.py --fix         # 自动修复

# 单项检查
uv run ruff check src/ tests/                       # lint
uv run ruff format src/ tests/                       # format
uv run vulture src/ --min-confidence 80             # dead code
uv run mypy src/ --ignore-missing-imports           # type check
```

## License

MIT
