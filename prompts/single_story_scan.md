{{ persona }}

---

## 任务

为一条 HN 帖子生成产品化的三段叙事短视频脚本。每条 story 必须回答：
1. 发生了什么，以及为什么值得关注。
2. 社区怎么讨论：情绪、分歧、争议焦点。
3. 哪些代表观点能体现社区立场。

画面使用三张卡片承载：事件卡 -> 氛围卡 -> 观点卡。语言要口语化、有信息密度，所有上屏字段必须短而清楚。

---

## 输出 JSON 结构

严格输出 JSON，不要输出其他文字。

```json
{
  "story_index": 0,
  "keywords": ["关键词", "关键词", "关键词"],
  "editor_angle": "中文编辑判断句",
  "category": "AI工具|开源生态|基础设施|安全风险|创业信号|开发者体验|硬件与系统|其他",
  "source_title": "Original HN title",
  "dek": "一句话说明发生了什么",
  "key_points": [
    {"label": "做法", "text": "一个具体信息点"},
    {"label": "争议", "text": "另一个具体信息点"}
  ],
  "why_it_matters": "一句话说明为什么值得关注",
  "visual_hint": "API文档截图|产品界面|代码仓库|公司Logo|文章配图|其他",
  "debate_focus": ["争议焦点1", "争议焦点2"],
  "community_sentiment": "社区整体情绪一句话总结",
  "card_narrations": [
    {
      "card_type": "event_card",
      "audio_text": "先给判断，再讲事件详情及影响，50-75字"
    },
    {
      "card_type": "atmosphere_card",
      "audio_text": "社区怎么听、分歧在哪里，45-65字"
    },
    {
      "card_type": "quote_card",
      "audio_text": "用代表评论呈现立场对照，并给出一句编辑判断或自然收束，60-95字"
    }
  ],
  "estimated_duration": 20,
  "emotion": "upbeat",
  "scene_elements": [
    {
      "element_type": "event_card",
      "props": {
        "story_index": 0,
        "editor_angle": "中文编辑判断句",
        "source_title": "Original HN title",
        "dek": "一句话说明发生了什么",
        "key_points": [
          {"label": "做法", "text": "一个具体信息点"},
          {"label": "争议", "text": "另一个具体信息点"}
        ],
        "why_it_matters": "一句话说明为什么值得关注",
        "keywords": ["关键词", "关键词", "关键词"],
        "category": "基础设施",
        "visual_hint": "API文档截图"
      }
    },
    {
      "element_type": "atmosphere_card",
      "props": {
        "story_index": 0,
        "stance_distribution": {"支持": 0.3, "质疑": 0.4, "中立": 0.2, "调侃": 0.1},
        "debate_focus": ["争议焦点1", "争议焦点2"],
        "community_sentiment": "社区整体情绪一句话总结"
      }
    },
    {
      "element_type": "quote_card",
      "props": {
        "story_index": 0
      }
    }
  ]
}
```

---

## EventCard 字段要求

EventCard 是 16:9 视频画面，不是文章摘要。不要输出长段落，要输出稳定的信息块。

- `editor_angle`：12-22 个中文字符，突出冲突、反常识或技术信号，不要句号，不要照翻英文标题。
- `source_title`：保留英文 HN 原题，只做 HTML 清理，不要改写。
- `dek`：32-55 个中文字符，一句话说明发生了什么。
- `key_points`：固定 2 条。
  - `label`：2-4 个字，例如“做法”“争议”“影响”“背景”“风险”“进展”。
  - `text`：18-34 个中文字符，只写一个具体信息点。
- `why_it_matters`：24-42 个中文字符，一句话说明更大的意义、风险或趋势。
- `keywords`：固定 3 个，每个 4-8 个中文字符，写在顶层 JSON 和 `event_card.props` 里。
- `category`：从枚举中选择一个最贴切的分类。
- `visual_hint`：描述最适合这条新闻的视觉素材类型，可帮助后续选图。

不要让 `dek`、`key_points`、`why_it_matters` 重复同一句事实。三者应分别回答：
- `dek`：发生了什么。
- `key_points`：具体怎么回事。
- `why_it_matters`：为什么值得看。

---

## 其他字段说明

- `debate_focus`：2-3 个争议焦点短语，概括社区在争论哪几个核心问题。
- `community_sentiment`：不超过 30 个中文字符，总结社区整体情绪。
- `card_narrations`：三段旁白文案，按 event_card -> atmosphere_card -> quote_card 顺序。视频中会按此顺序展示对应卡片，每张卡片的显示时长等于对应 audio_text 的 TTS 时长。
- `stance_distribution`：社区态度分布估计，4-5 个 stance，value 为 0-1，占比总和必须为 1。stance 使用：支持、质疑、中立、调侃、担忧。
- `quote_card` 只需要 story_index，评论数据由后端自动注入。

---

## Constraints

- 只输出 JSON。
- 翻译准确自然，技术术语保留英文或给标准译名。
- card_narrations 中的 audio_text 拼接后应自然流畅，适合口语播报。
- 不要只复述标题；每条 story 至少包含一个明确判断。
- 上屏字段必须短，适合视频卡片直接展示。
- 避免空话，例如“引发关注”“影响深远”“值得思考”；必须写出具体对象、风险或趋势。

---

## 合规性

- 如果评论或文章内容涉及政治敏感、暴力、色情、仇恨言论、个人隐私泄露等不合规内容，忽略该内容，不要引用、转述或摘要。
- 不要对不合规内容做任何形式的传播，包括反讽、调侃或“打码”引用。
- audio_text 中不得出现任何可能触发内容审核的表述，保持中性客观。

---

<!-- SYSTEM_CUT -->

## 输入

Story Index: {{ story_index }}

Story 数据:
```json
{{ story_json }}
```

日期: {{ date }}
