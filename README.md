# HN TechPulse

从 Hacker News 自动生成中文科技资讯视频的 Python 应用。项目目标不是简单搬运 HN 热榜，而是把当天高价值讨论整理成有筛选、有判断、有社区温度的技术日报视频。

## 功能特点

- 自动获取 Hacker News 热门故事和评论。
- 文章 enrich：抓取正文、图片、截图，并支持 Playwright 和 Bing 图片兜底。
- 评论分析与代表观点筛选：情绪、质量评分、引用惩罚、稳定翻译 key。
- LLM 生成中文视频脚本，支持 JSON 重试、截断后扩展 token 上限、并发 story 生成和 segment 缓存版本控制。
- TTS 语音合成（Edge TTS），并校验缓存音频与脚本文本的一致性。
- Remotion 视频渲染，包含 Dashboard、Event、Atmosphere、Quote、Closing 等卡片。
- 全局品牌角标、story 章节编号、底部 story 节点进度条。
- 细粒度缓存支持断点续跑，输出按日期存放在 `data/{date}/`。

## 当前重点

已完成的主要体验升级：

- EventCard 已优化信息层级、关键词数量、标题/正文溢出保护和图片降级策略。
- AtmosphereCard 已前置社区主情绪，并把争议指数做成可解释指标条。
- QuoteCard 已改为中文观点优先、一主两辅布局，并弱化英文原文。
- Remotion 默认使用 `src/providers/renderer/remotion/public/props.json` 作为开发预览 props。
- 评论管线重构：CommentAnalyzer 评分 → CommentJudge 预筛 → LLM 判断 → 脚本消费 `quote_candidates`，下游不再独立重选。
- 管线模块拆分：content_preparer、timing_engine、tts_processor、report_generator、script_io、transcript_generator。
- TS 质量门禁：Prettier、ESLint、tsc、Vitest、Knip、audit。

下一步优先事项见 [ROADMAP.md](ROADMAP.md)：标准版时长控制、标准版/完整版结构、EventCard 来源感、图片质量护栏和渲染前质量检查。

## 安装

```bash
# 使用 uv 安装依赖
uv sync
```

Remotion 子项目依赖：

```bash
cd src/providers/renderer/remotion
npm install
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

3. 根据需要修改 [config/](config/) 目录中的 YAML 配置文件（LLM 模型、TTS 语音、视频参数等，deep-merged）

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

# 只运行 TTS 和渲染
uv run python main.py --steps tts,render
```

可用步骤：

```text
fetch -> enrich -> analyze -> script -> translate -> tts -> render
```

`preview` 步骤可选，不在默认流程中。

### 其他选项

```bash
# 调试模式
uv run python main.py --debug

# 试运行（跳过 API 调用）
uv run python main.py --dry-run
```

### Remotion 预览

```bash
cd src/providers/renderer/remotion
npm run start
```

常用脚本：

```bash
npm run start   # 打开 Remotion Studio，读取 public/props.json
npm run still   # 渲染首帧预览图到 out/preview.png
npm run render  # 渲染视频到 out/output.mp4
```

## 项目结构

```
hn-techpulse/
├── src/
│   ├── core/           # 核心接口和数据模型
│   ├── providers/      # Fetcher/Enricher/LLM/TTS/Renderer 等服务提供者
│   ├── pipeline/       # 流程编排、评论分析、翻译、脚本生成、TTS 处理、时序引擎
│   ├── editor/         # Streamlit 脚本编辑器
│   └── utils/          # 工具模块
├── prompts/            # LLM 提示词模板
├── tests/              # 单元测试
├── scripts/            # 质量检查脚本（Python + TypeScript）
├── data/               # 输出数据目录
├── config/             # YAML 配置文件（deep-merged）
├── ROADMAP.md          # 产品和技术路线图
└── main.py             # 入口文件
```

## 测试

```bash
# 运行所有测试
uv run python -m pytest

# 运行特定测试文件
uv run python -m pytest tests/test_pipeline.py

# 运行最近重点覆盖的测试
uv run python -m pytest tests/test_article_enricher.py tests/test_remotion_renderer.py
```

## 代码质量

```bash
# Python 质量门禁（一站式）
uv run python scripts/quality_check.py              # 运行所有检查
uv run python scripts/quality_check.py --fix         # 自动修复

# TypeScript 质量门禁（Remotion 子项目）
cd src/providers/renderer/remotion
bash ../../../scripts/ts_quality_check.sh
```

## License

MIT
