{{ persona }}

---

## 任务

为一条 Hacker News story 生成「快扫」脚本。画面只有一张 `quick_item_card`。

只讲一个信息点，不展开评论，不做宏大总结。

---

## 输出 JSON 结构

严格输出 JSON，不要输出其他文字。

```json
{
  "story_index": 0,
  "category": "AI工具|开源生态|基础设施|安全风险|创业信号|开发者体验|硬件与系统|其他",
  "card_narrations": [
    {
      "card_type": "quick_item_card",
      "subtitle_texts": [
        "一句话讲清这条为什么值得扫过，28-48字。"
      ]
    }
  ],
  "estimated_duration": 8,
  "emotion": "neutral",
  "scene_elements": [
    {
      "element_type": "quick_item_card",
      "props": {
        "story_index": 0,
        "source_title": "Original HN title",
        "display_title": "中文短标题，10-22字",
        "quick_label": "工具|政策|开源|文章|Show HN|讨论",
        "micro_takeaway": "最小记忆点，12-26字"
      }
    }
  ]
}
```

---

## 写法

- 不要写评论区，除非评论比原帖更重要。
- 不要用"引发关注""值得关注""热议"。
- 不要说"第几条""接下来"。
- 宁可少讲，也不要塞两个事实。
- 严格只输出 1 条字幕，28-48 个中文字符。
- 不要使用“补刀”“吹嘘”“炸锅”“重磅”这类短视频口吻。

---

## 输入

Story Index: {{ story_index }}

Story 数据:
<story_json>
{{ story_json }}
</story_json>

日期: {{ date }}
