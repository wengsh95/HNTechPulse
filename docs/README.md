# 维护文档

日常使用只需要看项目根目录的 [README.md](../README.md)，运行：

```bash
uv run python main.py --date YYYY-MM-DD
```

项目始终沿着一条路走：

```text
Hacker News → 内容 → 视频
```

这里的其他文件是给维护者和自动化工具看的：

- [内部运行手册](internal/AGENT_RUNBOOK.md)：中断、恢复、审计。
- [内部结构说明](internal/PROJECT_STRUCTURE.md)：代码、缓存和产物。
- [自动代理指南](internal/AGENT_GUIDE.md)：只在维护自动运行时需要。
