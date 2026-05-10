
{{ persona }}

---

## 任务

为一条 HN 帖子生成 **产品化的三段叙事** 短视频脚本。每条 story 必须回答：

1. 发生了什么 + 为什么重要：事件摘要，含影响对象、趋势或产业含义。
2. 社区怎么吵：争议点、观点分布、争议焦点。

画面使用三张卡片承载：事件卡（发生了什么 + 为什么重要）→ 氛围卡（社区怎么吵）→ 观点卡（代表观点对照）。语言口语化、有信息密度。

---

## 输出 JSON 结构

严格输出 JSON，不要其他文字。

```json
{
  "story_index": 0,
  "keywords": ["关键词1", "关键词2", "关键词3"],
  "editor_angle": "中文编辑判断句（≤24字，不是标题直译）",
  "category": "AI工具|开源生态|基础设施|安全风险|创业信号|开发者体验|硬件与系统|其他",
  "debate_focus": ["争议焦点1", "争议焦点2"],
  "community_sentiment": "社区整体情绪一句话总结（≤30字）",
  "card_narrations": [
    {
      "card_type": "event_card",
      "audio_text": "先给判断，再讲事件详情及其影响（50-75字）"
    },
    {
      "card_type": "atmosphere_card",
      "audio_text": "社区怎么吵、分歧在哪里（45-65字）"
    },
    {
      "card_type": "quote_card",
      "audio_text": "用代表评论呈现立场对照，并给出一句编辑判断或自然收束（60-95字）"
    }
  ],
  "estimated_duration": 20,
  "emotion": "upbeat",
  "scene_elements": [
    {
      "element_type": "event_card",
      "props": {
        "story_index": 0,
        "event_summary": "事件简述（~100字，说清发生了什么、影响范围及值得关注的原因）",
        "editor_angle": "中文编辑判断句（≤24字）",
        "keywords": ["关键词1", "关键词2", "关键词3", "关键词4", "关键词5"]
      }
    },
    {
      "element_type": "atmosphere_card",
      "props": {
        "story_index": 0,
        "stance_distribution": {"支持": 0.3, "质疑": 0.4, "中立": 0.2, "担忧": 0.1},
        "debate_focus": ["争议焦点1", "争议焦点2"],
        "community_sentiment": "社区整体情绪一句话总结（≤30字）"
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

- `keywords`：5-8 个中文主题关键词，概括这条新闻的核心议题（如 "AI推理"、"开源争议"、"硅谷裁员"）。需同时写在顶层 JSON 和 event_card.props 中
- `editor_angle`：这条 story 的中文判断句，像栏目编辑给观众的第一眼结论；不要照翻英文标题
- `event_summary`：事件简述（~100字），用简短的话语说清发生了什么、影响范围及值得关注的原因
- `category`：从示例枚举里选一个最贴切的分类
- `debate_focus`：2-3 个争议焦点短语，概括社区在争论哪几个核心问题（如 "反垄断 vs 商业自由"、"技术可行性"）
- `community_sentiment`：≤30字，社区整体情绪一句话总结（如 "多数用户不满但讨论质量较高"）
- `card_narrations`：三段旁白文案，按 event_card → atmosphere_card → quote_card 顺序。video 中会按此顺序展示对应卡片，每张卡片的展示时长 = 对应 audio_text 的 TTS 时长
  - **event_card**（事件 + 判断）：先给编辑判断，再讲清楚事件详情及其影响，50-75字
  - **atmosphere_card**（氛围）：社区整体反应、观点分化情况，45-65字
  - **quote_card**（观点对照）：引用/概括具体评论观点，形成立场对照，并给出一句编辑判断或自然收束，60-95字
- `stance_distribution`：社区态度分布估计，5 个 stance（支持|质疑|中立|调侃|担忧），value 为占比（0-1，总和为1）
- `scene_elements`：3 个元素，按上述顺序排列。quote_card 只需 story_index 即可（评论数据由后端自动注入）

### constraints

- 只输出 JSON
- 翻译准确自然，技术术语保留英文或给标准译名
- card_narrations 中的 audio_text 拼接后应自然流畅，适合口语播报
- 不要只复述标题；每条 story 至少包含一个明确判断
- 画面字段要短：editor_angle 必须能一眼读完；event_summary 可稍长（~100字），需完整传达事件信息

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
