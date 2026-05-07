# HN TechPulse

从 Hacker News 生成科技新闻视频的 Python 应用。

## 功能特点

- 自动获取 Hacker News 热门故事和评论
- 使用 LLM 多轮对话生成视频脚本（R1a 分析 → R1b 决策 → R2 撰写）
- TTS 语音合成（支持 Edge TTS 和 OpenAI TTS）
- Remotion 视频渲染
- 细粒度缓存支持断点续传

## 安装

```bash
# 使用 uv 安装依赖
uv sync
```

## 配置

1. 复制环境变量示例：
```bash
cp .env.example .env
```

2. 编辑 `.env` 添加 API keys：
```env
OPENAI_API_KEY=your_api_key_here
```

3. 根据需要修改 [config.yaml](config.yaml) 中的配置（LLM 模型、TTS 语音、视频参数等）

## 使用

### 完整流程
```bash
python main.py
```

### 指定日期
```bash
python main.py --date 2026-04-26
```

### 运行特定步骤
```bash
# 只获取内容和生成脚本
python main.py --steps fetch,script

# 只运行 TTS 和渲染
python main.py --steps tts,render
```

### 其他选项
```bash
# 调试模式
python main.py --debug

# 试运行（跳过 API 调用）
python main.py --dry-run
```

## 项目结构

```
hn-techpulse/
├── src/
│   ├── core/           # 核心接口和数据模型
│   ├── providers/      # 各服务提供者（Fetcher/LLM/TTS/Renderer）
│   ├── pipeline/       # 流程编排
│   └── utils/          # 工具模块
├── prompts/            # LLM 提示词模板
├── data/               # 输出数据目录
├── config.yaml         # 主配置文件
└── main.py             # 入口文件
```

## 测试

```bash
# 运行所有测试
uv run pytest

# 运行特定测试文件
uv run pytest tests/test_pipeline.py
```

## License

MIT
