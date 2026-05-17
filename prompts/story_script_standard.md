{{ persona }}

---

## 任务

为一条 Hacker News story 生成「速读」脚本。画面只有一张 `story_compact_card`。

这不是重点深讲，只需要让听众知道：发生了什么、HN 为什么聊、一个可记住的角度。

语言：口语化、准确、短句。不强行制造共同主题。

---

## 输出 JSON 结构

严格输出 JSON，不要输出其他文字。

```json
{
  "story_index": 0,
  "category": "AI工具|开源生态|基础设施|安全风险|创业信号|开发者体验|硬件与系统|其他",
  "card_narrations": [
    {
      "card_type": "story_compact_card",
      "subtitle_texts": [
        "一句讲清发生了什么，25-38字。",
        "一句讲清HN在补充、吐槽或争论什么，22-34字。",
        "一句给记忆点，不要宏大升华，20-32字。"
      ]
    }
  ],
  "estimated_duration": 14,
  "emotion": "curious",
  "scene_elements": [
    {
      "element_type": "story_compact_card",
      "props": {
        "story_index": 0,
        "source_title": "Original HN title",
        "display_title": "中文短标题，12-24字",
        "reader_hook": "这条最值得看的问题，16-30字",
        "micro_takeaway": "一个具体 takeaway，16-32字"
      }
    }
  ]
}
```

---

## 写法

- 第一句必须有主语、动作、对象。
- 第二句根据 `discussion_mode` 写：debate 写分歧，field_notes 写经验补充，nostalgia 写怀旧点，correction 写纠错点。
- 第三句可以转述 `comment_lanes` 里的代表性 claim，但不要复制评论原文。
- 不要写"接下来""第几条""画面上"。
- 不要所有内容都写成"评论区争议焦点"。
- 严格只输出 3 条字幕，总字数 65-95 个中文字符。
- 不要使用“补刀”“吹嘘”“炸锅”“重磅”这类短视频口吻。

---

## 输入

Story Index: {{ story_index }}

Story 数据:
<story_json>
{{ story_json }}
</story_json>

日期: {{ date }}
