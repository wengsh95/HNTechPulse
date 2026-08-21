# HN TechPulse

把 Hacker News 新闻变成科技短视频。

## 它只做三件事

```text
采集素材 → 生成内容 → 生成视频
```

你给它新闻网站和 API 密钥，它最后会生成一个 MP4 视频。

## 开始使用

```bash
uv sync
cp .env.example .env
uv run python main.py --date 2026-04-26
```

视频会放在：

```text
data/2026-04/2026-04-26/publish/output.mp4
```

## 目录怎么看

| 目录 | 里面是什么 |
| --- | --- |
| `main.py` | 程序的开始按钮 |
| `src/` | 真正干活的代码 |
| `config/` | 参数，一般不用改 |
| `prompts/` | 写给 AI 的问题 |
| `assets/` | 字体和图片 |
| `data/` | 每天生成的结果 |
| `tests/` | 自动检查 |

## 常用按钮

- `--dry-run`：只看看会做什么，不调用 API
- `--resume`：上次中断了，从上次继续
- `--force`：重新生成视频

更多维护细节见 [docs/](docs/)。

## 检查代码

```bash
uv run python scripts/quality_check.py
```

## License

MIT
