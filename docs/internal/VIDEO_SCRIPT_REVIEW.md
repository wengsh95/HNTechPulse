# 视频文案人工审查流程

视频流程在自动文案审校之后、字幕与配音之前设置 `human_review` 闸门。
未经人工确认的脚本不会进入标题、分镜、字幕、TTS 或渲染阶段。

## 正常流程

```text
选题与评论分析
  → 生成台本
  → 准备人工审核（自动文案审校与定向改写）
  → 生成 script_review.html
  → 人工审查（流程阻塞）
  → 批准当前脚本版本
  → 评论翻译、标题与分镜
  → 字幕、TTS、渲染
```

启动视频生产：

```powershell
uv run python scripts/internal/agent/agent_run.py --date YYYY-MM-DD
```

流程到达人工闸门后会生成：

```text
data/YYYY-MM/YYYY-MM-DD/review/script_review.html
```

页面按段落显示当前连续口播、逐句字幕和自动审校评价。此时流水线状态为
`blocked`，原因为 `manual_script_review_required`。

确认页面中的当前版本后执行：

```powershell
uv run python scripts/internal/agent/agent_run.py --date YYYY-MM-DD --approve-script
```

该命令会写入 `agent/script_approval.json`，并从 `human_review` 恢复后续生产。
可以用 `--reviewer` 和 `--approval-note` 留下审查记录：

```powershell
uv run python scripts/internal/agent/agent_run.py --date YYYY-MM-DD `
  --approve-script --reviewer editor --approval-note "事实与评论已核对"
```

## 需要修改时

不要批准当前版本。先修改或重新生成 `pipeline/script.json`，再运行：

```powershell
uv run python scripts/internal/agent/agent_run.py --date YYYY-MM-DD --from human_review
```

流程会为新脚本重新生成审查页并再次阻塞。批准记录绑定
`script_editorial_hash`；任何旁白、字幕或场景文案变化都会使旧批准自动失效。

即使直接执行 `--from prepare_subtitles`、`--from apply_storyboard` 或请求
`render`，主流程也会注入 `human_review`，不能绕过人工确认。
