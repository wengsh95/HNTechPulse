
{{ persona }}

---

## 任务

为一条 HN 帖子生成 **三段递进式** 短视频脚本（事件 → 氛围 → 社区原声）。语言口语化、有信息密度。

---

## 输出 JSON 结构

严格输出 JSON，不要其他文字。

```json
{
  "story_index": 0,
  "keywords": ["关键词1", "关键词2", "关键词3"],
  "card_narrations": [
    {
      "card_type": "event_card",
      "audio_text": "事件简述旁白（40-60字）"
    },
    {
      "card_type": "atmosphere_card",
      "audio_text": "社区氛围旁白（40-60字）"
    },
    {
      "card_type": "quote_card",
      "audio_text": "评论观点旁白（60-100字）"
    }
  ],
  "estimated_duration": 20,
  "emotion": "upbeat",
  "scene_elements": [
    {
      "element_type": "event_card",
      "props": {
        "story_index": 0,
        "event_summary": "事件简述（≤40字，一句话说清发生了什么事）",
        "keywords": ["关键词1", "关键词2", "关键词3"]
      }
    },
    {
      "element_type": "atmosphere_card",
      "props": {
        "story_index": 0,
        "stance_distribution": {"支持": 0.3, "质疑": 0.4, "中立": 0.2, "担忧": 0.1}
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

### 字段说明

- `keywords`：3-5 个中文主题关键词，概括这条新闻的核心议题（如 "AI推理"、"开源争议"、"硅谷裁员"）
- `card_narrations`：三段旁白文案，按 event_card → atmosphere_card → quote_card 顺序。video 中会按此顺序展示对应卡片，每张卡片的展示时长 = 对应 audio_text 的 TTS 时长
  - **event_card**（事件）：讲清楚"发生了什么事"，40-60字
  - **atmosphere_card**（氛围）：社区整体反应、观点分化情况，40-60字
  - **quote_card**（原声）：引用具体评论观点，60-100字
- `event_summary`：≤40字，一句话事件摘要，在 event_card 上展示
- `stance_distribution`：社区态度分布估计，5 个 stance（支持|质疑|中立|调侃|担忧），value 为占比（0-1，总和为1）
- `scene_elements`：3 个元素，按上述顺序排列。quote_card 只需 story_index 即可（评论数据由后端自动注入）

### constraints

- 只输出 JSON
- 翻译准确自然，技术术语保留英文或给标准译名
- card_narrations 中的 audio_text 拼接后应自然流畅，适合口语播报

### 合规性

- 如果评论或文章内容涉及政治敏感、暴力、色情、仇恨言论、个人隐私泄露等不合规内容，**忽略该内容**，不要引用、转述或摘要
- 不要对不合规内容做任何形式的传播，包括反讽、调侃或"打码"引用
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

