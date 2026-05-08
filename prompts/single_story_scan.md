
{{ persona }}

---

## 任务

为一条 HN 帖子生成 **story_scan** 中的单条内容。

这是每日快讯（daily_brief）产品的一部分：每条新闻快速扫过，8-12秒，包含事件简述 + 2-3个观点摘要。

---

## 输出 JSON 结构

严格输出 JSON，不要其他文字。

```json
{
  "story_index": 0,
  "event_summary": "事件简述——这条新闻说的是什么事（≤40字，一句话说清）",
  "viewpoints": [
    {
      "stance": "支持|质疑|中立|调侃|担忧",
      "summary": "观点摘要（≤20字，极简）",
      "quote": "评论原文片段（≤50字，保留原汁原味）",
      "comment_index": 5
    },
    {
      "stance": "支持|质疑|中立|调侃|担忧",
      "summary": "观点摘要（≤20字，极简）",
      "quote": "评论原文片段（≤50字，保留原汁原味）",
      "comment_index": 3
    }
  ],
  "audio_text": "完整配音文案——将事件简述和观点自然串起来，约80-120字",
  "estimated_duration": 10,
  "emotion": "upbeat",
  "stance_distribution": {"支持": 0.4, "质疑": 0.3, "中立": 0.2, "担忧": 0.1},
  "scene_elements": [
    {
      "element_type": "story_scan_card",
      "props": {
        "story_index": 0,
        "event_summary": "事件简述",
        "viewpoints": [
          {
            "stance": "支持",
            "summary": "观点摘要",
            "quote": "评论原文片段",
            "comment_index": 5
          }
        ],
        "stance_distribution": {"支持": 0.4, "质疑": 0.3, "中立": 0.2, "担忧": 0.1}
      }
    }
  ]
}
```

### 字段说明

- `event_summary`: 必须讲清楚"发生了什么事"，不是复述标题
- `viewpoints`: 2-3个，覆盖不同 stance（不要只支持和质疑）
- `viewpoint.summary`: ≤20字，观众扫一眼就懂
- `viewpoint.quote`: ≤50字，从真实评论摘取原文片段
- `audio_text`: 80-120字，自然流畅，适合口语播报
- `stance_distribution`: 你对整条帖子下所有评论的态度分布估计，key 为 stance（支持|质疑|中立|调侃|担忧），value 为该态度的占比（0-1，总和为1）。仅统计你在 viewpoints 中引用了的 stance 即可。
- `scene_elements`: 只需 story_scan_card，无需指定 start_time/end_time（由 TTS 音频时长决定）。props 包含 story_index, event_summary, viewpoints, stance_distribution

### constraints

- 只输出 JSON
- 翻译准确自然，技术术语保留英文或给标准译名
- 当故事有图片时（has_images=true），在 scene_elements 中添加一个 image_card

### 合规性

- 如果评论或文章内容涉及政治敏感、暴力、色情、仇恨言论、个人隐私泄露等不合规内容，**忽略该内容**，不要引用、转述或摘要
- 不要对不合规内容做任何形式的传播，包括反讽、调侃或"打码"引用
- 如果某条评论不合规，跳过它，从其他合规评论中选取 viewpoints
- 如果所有评论均不合规，viewpoints 留空，audio_text 仅做事件简述
- audio_text 中不得出现任何可能触发内容审核的表述，保持中性客观

---

&lt;!-- SYSTEM_CUT --&gt;

## 输入

Story Index: {{ story_index }}

Story 数据:
```json
{{ story_json }}
```

日期: {{ date }}

