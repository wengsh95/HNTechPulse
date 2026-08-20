# 视频分镜模板选择

视频流水线支持在 `data/YYYY-MM/YYYY-MM-DD/pipeline/storyboard.json` 中为
已有场景选择 Remotion 镜头模板。它是“镜头选择层”，不负责新增旁白，也不
修改字幕和音频时长。

分镜发生在文案人工批准之后。文案审查与批准命令见
[`VIDEO_SCRIPT_REVIEW.md`](VIDEO_SCRIPT_REVIEW.md)。

## 每个 story 的图片硬约束

视频流程在 `prepare_story_images` 阶段为每个 story 解析至少一张本地图片，
并写入 `pipeline/story_images.json`。图片会同步注入该 story 的所有场景元素
的 `image_src` / `story_image`，由 Remotion 模板选择合适的图片区域呈现。

图片来源按以下顺序收集：已有文章配图、已有截图或图片候选、来源页截图；
来源页无法访问时，最后回退到对应 HN 讨论页截图。Agent 模式下没有确认的
本地候选会阻塞流水线，不允许无图继续渲染。确认后把候选的精确相对路径写入
`pipeline/image_selection.json` 的 `selected_image`。

## 最小格式

```json
{
  "schema_version": 1,
  "date": "2026-08-18",
  "shots": [
    {
      "shot_id": "H01-01",
      "story_index": 0,
      "source_element_type": "event_card",
      "source_element_index": 0,
      "template_id": "headline_v1",
      "props": {
        "title": "这个变化为什么值得关注",
        "eyebrow": "头条",
        "source_label": "news.ycombinator.com"
      }
    },
    {
      "shot_id": "H01-02",
      "story_index": 0,
      "source_element_type": "atmosphere_card",
      "source_element_index": 0,
      "template_id": "comment_dual_v1",
      "props": {
        "left_summary": "支持者认为它降低了使用门槛",
        "right_summary": "反对者担心成本和可控性",
        "left_label": "支持",
        "right_label": "质疑"
      }
    }
  ]
}
```

`story_index` 和 `source_element_index` 都是从 0 开始。也可以用更机械但更
稳定的 `segment_index` + `element_index` 直接定位 `script.json` 中的元素。
重复执行时会优先按 `shot_id` 找回已经应用过的镜头，因此不会因为原始元素
类型已经变成新模板而失效。

## 可选模板

| template_id | 用途 |
| --- | --- |
| `headline_v1` | 头条钩子 |
| `source_evidence_v1` | 原文/截图/来源证据 |
| `comment_single_v1` | 单条 HN 评论 |
| `comment_dual_v1` | 两种观点对照 |
| `data_number_v1` | 一个关键数字 |
| `quick_news_v1` | 快讯 |
| `closing_signals_v1` | 结尾三条信号 |
| `event_v1`, `discussion_v1`, `cover_v1`, `closing_v1` | 兼容旧模板 |

应用分镜并重做后续视频：

```powershell
uv run python scripts/agent_run.py --date 2026-08-18 --from apply_storyboard
```

如果还没有分镜，先让 agent 生成一份不会覆盖人工编辑的初稿：

```powershell
uv run python scripts/agent_run.py --date 2026-08-18 --steps draft_storyboard
uv run python scripts/generate_video_review.py --date 2026-08-18
```

生成“台本段落 ↔ 对应镜头”的本地预览页：

```powershell
uv run python scripts/generate_video_review.py --date 2026-08-18
```

输出在 `data/YYYY-MM/YYYY-MM-DD/review/video_review.html`。每个段落会先显示
旁白，下面紧跟该段落的镜头、模板、画面文字和对应台词。

没有 `storyboard.json` 时，`apply_storyboard` 是安全空操作，旧的
`event_card` / `atmosphere_card` 流程保持不变。
