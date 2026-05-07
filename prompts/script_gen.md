{{ persona }}

---

## 任务

基于选题编辑的精选材料，写出完整视频脚本。采用深度分级模板：

- Module 0: 今日HN仪表盘 (8-12s) — 终端风格，列出帖子标题及翻译
- Module 1: Top1深度深挖 (55-65s) — 最热/争议最大，展示阵营对立和精选评论
- Module 2-3: Top2-3标准播报 (25-35s/条) — 有价值的技术文章/行业新闻
- Module 4: Top4-5快速扫描 (12-18s/条) — 有趣但不必展开的小项目/小新闻

---

## 输出 JSON 结构

严格输出 JSON，不要其他文字。segments 必须包含 opening/deep_dive/medium_dive/quick_news/closing 五种类型。

```json
{
  "title": "", "description": "", "tags": [],
  "deep_dive": {
    "context": "2-3句背景",
    "featured_comments": [{"author":"","score":0,"text":"原文","translation":"译文","angle_brief":"角度"}],
    "viewpoint_camps": [
      {"position":"阵营立场","key_points":["论点1"],"representative_quote":"代表发言","quote_author":"发言者"}
    ],
    "selected_comments": [
      {"author":"","text":"","sentiment":"neutral|positive|negative|controversial"}
    ],
    "perspective_a": {"label":"","core_argument":"","representative_comment":{"author":"","text":"原文","translation":"译文"}},
    "perspective_b": {"label":"","core_argument":"","representative_comment":{"author":"","text":"原文","translation":"译文"}},
    "synthesis": ["洞察1","洞察2"],
    "host_take": "主播一句话态度（必填）"
  },
  "medium_items": [
    {"story_index":0,"summary":"","featured_comment":{"author":"","score":0,"text":"原文","translation":"译文"},"transition_note":"过渡/吐槽/点评（必填）","info_table":[{"label":"","value":""}]}
  ],
  "quick_items": [
    {"story_index":0,"summary":"","featured_comment":{"author":"","score":0,"text":"原文","translation":"译文"},"transition_note":"过渡/吐槽/点评（必填）"}
  ],
  "segments": [
    {
      "segment_type": "opening",
      "audio_text": "完整配音文案",
      "script_segments": ["分段1", "分段2"],
      "estimated_duration": 10,
      "emotion": "curious",
      "cues": [{"text":"短句1","start_time":0,"end_time":5},{"text":"短句2","start_time":5,"end_time":10}],
      "scene_elements": [
        {"element_type":"title_card","start_time":0,"end_time":10,"props":{"title":"HN TechPulse","subtitle":"<今日日期>","stats":""}}
      ],
      "meta": {}
    }
  ]
}
```

以上仅展示 opening 作为格式参考，你需要输出全部 5 种 segment_type。

### segments 各段要求

| type | 时长 | emotion | scene_elements | 要点 |
|------|------|---------|----------------|------|
| opening | 8-12s | curious | title_card | 日期 + 简短问候 + deep_dive 故事的钩子（必须与 deep_dive 话题一致，不要提不做 deep_dive 的 top post） |
| deep_dive | 55-65s | analytical | story_header, comment_card×2, perspective_compare, synthesis_card | audio_text ≥ 250 中文字，聚焦核心故事，精炼展开 |
| medium_dive | 25-35s/条 | engaged | story_header, comment_bubble | audio_text ≥ 120 中文字，每个帖子一条独立 segment，必须包含：故事背景(1句) + 精选评论解读(2句) + 主播点评(1句)，清晰过渡 |
| quick_news | ~40-60s | upbeat | news_carousel_card（每条新闻一个） | 最多4条，每条12-18s（audio_text ≥ 60中文字/条），轻快推进 |
| closing | 10-15s | warm | closing_card | 思考题或金句收尾，不用"感谢收看" |

### script_segments 分段规则

每个 segment 的 audio_text 必须同时提供 script_segments（字符串列表），将完整文案拆分为适合字幕显示的短句：
- 每段 15-25 个中文字符
- 在句号、逗号、感叹号、问号等自然断点处断开
- 优先在语义完整处断开，不要在短语或术语中间断开
- 所有分段拼接后应与原始 audio_text 内容一致（允许标点微调）
- deep_dive 分段数约 5-8 段，medium_dive 约 3-5 段，quick_news 每条约 1-2 段，opening 约 2-3 段，closing 约 2-3 段

### scene_elements props 要求

**重要：scene_elements 的 props 只需包含索引引用，完整内容将从原始数据自动填充。**

- `story_header`: `{"story_index": N}` - story_index 对应输入中的故事索引，title/score/comment_count 自动填充
- `comment_card`: `{"story_index": N, "comment_index": M}` - 从该故事中选取第 M 条评论，自动填充
- `comment_bubble`: `{"story_index": N, "comment_index": M}` - 同上
- `news_carousel_card`: `{"story_index": N, "comment_index": M}` - 同上
- `perspective_compare`: `{"perspective_a": {"story_index": N, "comment_index": M}, "perspective_b": {"story_index": N, "comment_index": M}}`
- `synthesis_card`: `{"points": ["洞察1", "洞察2"]}` - points 需要完整文本
- `title_card`, `closing_card`: props 需要完整文本（title, subtitle, stats, quote, question 等）
- `dashboard_card`: `{"entries": [{"rank": 1, "story_index": 0}, ...]}` - title/score/comment_count 自动填充
- `image_card`: `{"story_index": N, "image_index": M, "caption": "图片说明"}` - 展示第 N 个故事的第 M 张文章配图，caption 为简短中文说明

### cues 要求

- 将 audio_text 拆分为15-25字短句，每句一条 cue
- start_time/end_time 与朗读节奏对齐，覆盖 0 到 estimated_duration，无间隙

## 约束

1. 只输出 JSON
2. 总时长 3-4 分钟
3. 翻译准确自然，技术术语保留英文或给标准译名
4. Synthesis 是核心价值——提炼洞察，不是复读
5. host_take、transition_note、closing_question 必填
6. medium_dive 和 quick_news 的 scene_elements 包含每条新闻的卡片
7. 时间轴合理衔接，不重叠不空白
8. 消除冗余：严禁输出重复观点，合并所有总结、洞察和风险
9. 做减法：把厚重的研报拍扁，变成观众愿意一边吃外卖一边看的"电子榨菜"
10. deep_dive 必须拆解观点阵营（viewpoint_camps），展示对立立场
11. opening 必须与 deep_dive 话题一致——用 deep_dive 故事最有冲击力的点做开场，不要提不进入 deep_dive 的 top post（避免叙事断裂）
12. deep_dive 的 audio_text 必须 ≥ 250 中文字（约55-65s @4字/秒），确保内容充实不注水
13. medium_dive 的 audio_text 必须 ≥ 120 中文字，且包含三层结构：(1) 故事背景1句 (2) 精选评论解读2句 (3) 主播点评1句。禁止只有1句话+1条评论的薄内容
14. quick_news 最多4条，每条 audio_text ≥ 60 中文字（约12-18s），禁止4条塞进15s
15. 当故事有图片时（has_images=true），在 deep_dive 或 medium_dive 段中添加 1 个 image_card 场景元素，展示最能说明文章内容的图片

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
