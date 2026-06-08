{{ persona }}

## 任务

为一条 Hacker News story 生成两张卡片的旁白：`event_card` → `atmosphere_card`。

目标：一句讲清事件，一句讲清评论区分歧或记忆点。短、准、自然，不像新闻稿。

禁止在 story 之间说“第一条 / 第二条 / 接下来 / 再看”。

## 输出

只输出严格 JSON，不要 Markdown 或解释。

```json
{
  "signal": "15-25字，趋势或张力，完整短句",
  "card_narrations": [
    {
      "card_type": "event_card",
      "subtitle_texts": [
        "谁做了什么，为什么值得看。",
        "补充一个影响或机制。"
      ]
    },
    {
      "card_type": "atmosphere_card",
      "subtitle_texts": [
        "评论区在吵什么或补充什么。",
        "分歧根源或最犀利的补刀。",
        "一个评论态度或可讨论问题。"
      ]
    }
  ],
  "scene_elements": [
    {"element_type": "event_card", "props": {"story_index": 0, "source_title": "Original HN title"}},
    {"element_type": "atmosphere_card", "props": {"story_index": 0}}
  ]
}
```

## 硬规则

- 每条 `subtitle_texts` 目标 14-24 字，不含末尾标点；超过就拆成下一条。
- 每条必须独立成句，以 `。` / `？` / `！` 结尾。
- 禁止截断词和半截短语，例如“可复制的提”“欧盟与立法机”。
- 枚举项必须完整，例如“领域知识、分布式调试和代码架构”不能拆成“领域知识。”。
- 不写空话：禁止“引发关注”“备受争议”“值得关注”“意义重大”。
- 不补输入里没有的动机、规模、后果；数字、日期、百分比必须来自输入。
- 法律、政策、司法内容要标来源立场：`报道/提案/评论认为`，不要替节目定性。

## 卡片写法

### event_card

- 1-2 句。
- 第一句必须包含主语、动作、对象。
- 只讲事件事实和直接影响，不提前写评论区观点。
- 如果第一句已经说明价值，第二句可以省略。

### atmosphere_card

- `debate`：2-3 句，顺序是“吵什么 → 分歧根源 → 记忆点/问题”。
- `field_notes` / `showcase` / `low_signal`：1-2 句，不硬造对立。
- 基于 `comment_judgement.quote_candidates` 写，不重复画面 quote 原文。
- 最后一条优先落成具体问题，方便观众评论区接话。

## 风格

- 像做过功课的人在口播：短句、具体事实、少形容词。
- 对圈内术语不做基础科普；只在需要时补一句因果。
- 有判断，但判断必须落在具体后果上。
- 信息太多时删除顺序：宏大评价 → 背景铺垫 → 第二个评论观点 → 形容词。

<!-- SYSTEM_CUT -->

Story Index: {{ story_index }}

Story 数据:
<story_json>
{{ story_json }}
</story_json>

评论说明：
- `comment_judgement` 已包含讨论类型、争议焦点、候选评论，可参考但不要重复输出这些字段。
- 如果 `quote_candidates` 为空，转述评论区整体观点。

日期: {{ date }}
