{{ persona }}

---

## 任务

生成"每日快讯"视频脚本——让观众 120-150 秒内扫完今天 HN 热门，并了解每条新闻的事件和社区观点。

产品定位：信息仪表盘 + 逐条速览。不做深度分析，不做阵营拆解。核心价值是"帮你快速扫完今天的 HN，顺便听听大家怎么看"。

---

## 输出 JSON 结构

严格输出 JSON，不要其他文字。segments 包含 opening / dashboard / story_scan / closing 四种类型。

```json
{
  "title": "",
  "description": "",
  "tags": [],
  "brief_items": [
    {
      "story_index": 0,
      "event_summary": "事件简述——这条新闻说的是什么事（≤40字）",
      "viewpoints": [
        {"stance": "支持|质疑|中立|调侃|担忧", "summary": "观点摘要（≤20字）", "quote": "评论原文片段（≤50字）", "comment_index": 5}
      ]
    }
  ],
  "segments": [
    {
      "segment_type": "opening",
      "audio_text": "完整配音文案",
      "script_segments": ["分段1", "分段2"],
      "estimated_duration": 7,
      "emotion": "warm",
      "cues": [{"text": "短句1", "start_time": 0, "end_time": 4}],
      "scene_elements": [
        {"element_type": "title_card", "start_time": 0, "end_time": 7, "props": {"title": "HN TechPulse", "subtitle": "<今日日期>", "stats": ""}}
      ],
      "meta": {}
    }
  ]
}
```

以上仅展示 opening 作为格式参考，你需要输出全部 4 种 segment_type。

### segments 各段要求

| type | 时长 | emotion | scene_elements | 要点 |
|------|------|---------|----------------|------|
| opening | 5-8s | warm | title_card | 固定问候 + 日期。不用钩子，不用悬念，像跟朋友打招呼 |
| dashboard | 10s | neutral | dashboard_card | 纯视觉展示热度榜列表。audio_text 仅一句极短过渡语（如"先看看今天的热度榜"），主要靠画面 |
| story_scan | 80-120s | upbeat | story_scan_card（每条一个） | 逐条速览，每条8-12s。audio_text 包含事件简述 + 2-3个观点摘要。节奏轻快 |
| closing | 5-8s | warm | closing_card | 固定结尾："下期再见，多喝热水" |

### opening 固定文案模板

audio_text 必须包含以下要素（可微调措辞，但结构和内容固定）：
- 问候："大家好，我是小P"
- 日期："今天是{{ date_display }}"
- 引导："来看看今天 Hacker News 上有什么新鲜事"

### closing 固定文案

audio_text 固定为："好，今天的速览就到这里，下期再见，多喝热水。"

### script_segments 分段规则

- 每段 15-25 个中文字符，在自然断点处断开
- opening 约 2-3 段，dashboard 约 1 段，story_scan 约 15-25 段，closing 约 2 段

### scene_elements props 要求

- `title_card`: `{"title": "HN TechPulse", "subtitle": "日期", "stats": "热门速览"}`
- `dashboard_card`: `{"entries": [{"rank": 1, "story_index": 0}, ...]}` — rank 和 story_index 即可，title/score/comment_count 将从原始数据自动填充
- `story_scan_card`: `{"story_index": N, "event_summary": "事件简述", "viewpoints": [{"stance": "支持", "summary": "...", "quote": "...", "comment_index": M}]}` — story_title/title_cn/score/comment_count/stance_distribution 将从原始数据自动填充
- `closing_card`: `{"text": "下期再见，多喝热水"}`
- `image_card`: `{"story_index": N, "image_index": 0, "caption": "图片说明"}` - 展示文章配图

### cues 要求

- 将 audio_text 拆分为15-25字短句，每句一条 cue
- start_time/end_time 覆盖 0 到 estimated_duration，无间隙
- dashboard 段 cues 极少（1-2条过渡语即可）

## 约束

1. 只输出 JSON
2. 总时长 120-150 秒
3. 翻译准确自然，技术术语保留英文或给标准译名
4. **每条 brief_item 必须有 event_summary**——说清楚这件事是什么，不是复述标题
5. **每条 brief_item 必须有 2-3 个 viewpoints**——来自评论区不同立场，每个标注 stance
6. **viewpoint.summary ≤ 20字**——极简，观众扫一眼就懂
7. **viewpoint.quote ≤ 50字**——从真实评论摘取原文片段，保留原汁原味
8. **stance 只用以下标签**：支持、质疑、中立、调侃、担忧
9.  **每条 brief_item 的 viewpoints 必须覆盖 ≥3 种不同 stance**——不要只出"支持"和"质疑"
10. **stance_distribution 不需要输出**——将从评论数据自动计算
11. opening 和 closing 的文案遵循固定模板，不自由发挥
12. dashboard 段 audio_text 极短，不超过 15 字
13. 节奏：opening 简洁 → dashboard 静默展示 → story_scan 轻快扫过 → closing 温暖收尾
14. brief_items 按 HN 排名顺序排列
15. 当故事有图片时（has_images=true），可在对应的 story_scan_card 同一 segment 中添加 1 个 image_card，展示文章配图

<!-- SYSTEM_CUT -->

## 输入

选题决策：
```json
{{ selection_json }}
```

精选评论：
```json
{{ comments_json }}
```

日期：{{ date }}
