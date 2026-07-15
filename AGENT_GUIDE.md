# AGENT_GUIDE.md（中文版）

HN TechPulse 是一个 Python CLI 流水线（非 Web 应用），用于从 Hacker News 内容生成每日科技新闻视频简报。本指南面向运行该流水线的编码 Agent（自动化代理），提供操作规范与最佳实践。

完整的项目结构与架构说明见 [CLAUDE.md](CLAUDE.md)；Agent 契约（状态文件、阻塞原因、决策门、步骤处理策略、变体）见 [docs/AGENT_RUNBOOK.md](docs/AGENT_RUNBOOK.md)；模块清单见 [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md)。

## 快速开始

流水线由 `scripts/agent_run.py` 统一调度，内部依次执行：

1. **preflight**（预检）：校验环境与配置
2. **status**（状态检查）：读取 `pipeline_state.json`
3. **safe steps**（安全步骤）：仅执行不会破坏既有产物的步骤
4. **audit**（审计）：在 `main.py --agent` 完成后调用 `agent_audit.py`

## 关键命令

```bash
# 1. 受管 Agent 运行（preflight + status + 安全步骤）
uv run python scripts/agent_run.py --date YYYY-MM-DD

# 2. 从中断处续跑
uv run python scripts/agent_run.py --date YYYY-MM-DD --resume

# 3. 检查机器可读的状态与产物
uv run python scripts/agent_status.py --date YYYY-MM-DD

# 4. 发布前最终可发布性审计
uv run python scripts/agent_audit.py --date YYYY-MM-DD

# 5. 运行测试
uv run python -m pytest
```

**禁止**直接调用 `main.py --agent`。该入口有保护逻辑，会拒绝直接的 Agent 调用；手动调试可使用 `main.py --agent --direct-agent-run`，但自主运行的 Agent 必须始终使用 `scripts/agent_run.py`。

## 关键参考

- **完整指南**：[CLAUDE.md](CLAUDE.md) — 架构、模式、陷阱、行为规则
- **Agent 契约**：[docs/AGENT_RUNBOOK.md](docs/AGENT_RUNBOOK.md) — 状态文件、阻塞原因、决策门、步骤处理策略、变体
- **模块清单**：[docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md)

## 状态文件（位于 `data/{date}/agent/`）

| 文件 | 用途 |
|------|------|
| `pipeline_state.json` | 流水线状态、已完成/失败步骤、阻塞原因 |
| `agent_events.jsonl` | 仅追加的事件日志 |
| `agent_tasks.json` | 待修复任务清单（如手动抓取文章） |
| `agent_decision.json` | 决策门结果（置信度、分数、阈值） |

> 注：`data/{date}/agent/` 为权威目录；旧版脚本可能直接写到 `data/{date}/`，以 `docs/AGENT_RUNBOOK.md` 为准。

## 规则

1. **始终使用** `scripts/agent_run.py` 运行流水线；它会在调用 `main.py --agent` 之前先做 preflight 与 status 检查。
2. **读取 JSON 状态文件**，不要解析人类可读的日志。
3. **遇到 `blocked` 状态** → 读取 `pipeline_state.json` 中的 `blocked_reason` → 按 [AGENT_RUNBOOK.md](docs/AGENT_RUNBOOK.md) 处理。
4. **未经用户明确批准**，禁止在最终输出上使用 `--allow-degraded-enrichment`。
5. 若 `agent_status.py` 报告产物陈旧（stale），按其 `safe_next_commands` 处理；不要用陈旧的 `script.json` / `cli_props.json` 组合去渲染。

## 架构概览

HN TechPulse 的入口为 [main.py](main.py) → [src/pipeline/orchestrator.py](src/pipeline/orchestrator.py)，按以下三组步骤执行：

- **默认链（16 步）** — `scripts/agent_run.py` 默认运行的内容：核心 12 步 + `cover_image` + `cover_thumbnail` + `publish_guide` + `render`
- **核心链（12 步）** — `fetch … title, prepare_render`，不含生产三人组；可通过 `--steps` 子链运行
- **独立（1 步）** — `preview`，始终需显式启用（成功渲染后做人工质检）

数据流（简化）：

```
HN API → fetch → prefilter → fetch_comments → enrich_articles → translate_titles
  → analyze_comments → judge_comments → write_script
  → translate_comments → synthesize_audio → title
  → cover_image → cover_thumbnail → publish_guide → prepare_render → render
                                                                              ↓ (opt-in)
                                                                            preview
```

**关键原则**：CommentAnalyzer 打分 → CommentJudge 选出 `quote_candidates` → ScriptWriter 直接消费；下游不再做独立重选。

详细数据流、缓存文件清单与产物布局，见 [CLAUDE.md](CLAUDE.md)。

## 关键模式

- **Provider 工厂**：在 [src/providers/factory.py](src/providers/factory.py) 的 `_auto_register()` `attempts` 列表中添加 `(kind, name, module_path, class_name, register_fn)` 元组；类必须实现 [src/core/interfaces.py](src/core/interfaces.py) 中的 ABC。注册在导入时执行；依赖缺失会被静默跳过。
- **LLM JSON 重试**：`_call_llm_with_json_retry()` 在 JSON 无效时重试，`finish_reason=length` 时翻倍 `max_tokens`；通过 `llm.max_completion_tokens_cap` 限制封顶。
- **双模型 LLM**：主模型用于脚本，`fast` 模型（更低 token / 温度）用于翻译与评论打分。
- **Prompt 占位符**：`{{ placeholder }}` 必须是 [src/core/prompts.py](src/core/prompts.py) 中的 `PH_*` 常量；拼写错误时 `render_prompt()` 抛 `ValueError`。
- **并发**：`llm.max_workers` 控制故事并发，`analyze.comment_judge_max_workers` 控制评论打分并发。改 segment-cache 语义时记得 bump `llm.cache_schema_version`。
- **死代码**：用 `vulture` 与 `ruff --select F` 检测；自动注册的 Provider 类可能误报。

## 工具与环境陷阱

### Windows 路径

- Git Bash 把盘符挂载为 `/c/`、`/d/`，**不是** `C:\`、`D:\`。
- PowerShell 用 `D:\` 加 `Set-Location`；不要混用。

### PowerShell 编码

如果中文输出乱码，执行 `. .\scripts\encoding.ps1`（设置 `PYTHONUTF8=1`、`chcp 65001`）。

### Remotion 渲染文件名

h264+aac 要求输出文件名后缀为 `.mp4` / `.mkv` / `.mov`。使用 `.partial.mp4`，**不要**用 `.mp4.partial`。详见 [remotion_renderer.py:285](src/providers/renderer/remotion_renderer.py#L285)。

## 行为准则

> 取舍：偏向保守。琐碎任务酌情处理。

1. **先确认再写代码** — 提交实现前给出方案并获批准；琐碎修复豁免。
2. **先思考再写代码** — 明确假设；多种解释时一并列出；不确定就问。
3. **简洁优先** — 最小代码量。无投机性功能、无一次性抽象、无针对不可能场景的错误处理。
4. **手术式改动** — 只动必须改的；贴合既有风格；只删自己的孤儿；每一处改动都要能溯源到需求。
5. **目标驱动** — 定义可验证的成功标准，循环到验证通过。
6. **思考与编码分离** — 计划阶段聚焦权衡与方法，不要"以防万一"地预写代码。

---

> 本文件为中文版摘要；权威说明以 [CLAUDE.md](CLAUDE.md) 与 [docs/AGENT_RUNBOOK.md](docs/AGENT_RUNBOOK.md) 为准。英文 / 中文若有不一致，以英文为准。