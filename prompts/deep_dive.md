{{ persona }}

---

## 任务

生成"深度解读"视频脚本——围绕**一个话题**做透彻分析，让观众看完后能拿去饭桌上跟人聊。

产品定位：单话题深挖。核心价值是"观点输出 + 评论区挖掘"——你做的是别人替代不了的解读，不是信息搬运。

---

## 输出 JSON 结构

严格输出 JSON，不要其他文字。segments 包含 opening / context / viewpoint_a / viewpoint_b / comment_deep / synthesis / closing 七种类型。

```json
{
  "title": "",
  "description": "",
  "tags": [],
  "deep_dive": {
    "story_index": 0,
    "context": "2-3句话背景——这个话题为什么今天被热议",
    "core_tension": "核心张力——一句话概括这件事的冲突本质",
    "viewpoint_camps": [
      {
        "position": "阵营立场名称",
        "key_points": ["论点1", "论点2"],
        "representative_quote": "代表发言原文",
        "quote_author": "发言者",
        "quote_translation": "译文"
      }
    ],
    "selected_comments": [
      {
        "author": "",
        "text": "评论原文",
        "translation": "译文",
        "sentiment": "neutral|positive|negative|controversial",
        "why_notable": "为什么这条评论值得注意（1句话，不是总结内容，是点出这个视角的独特之处）"
      }
    ],
    "synthesis": ["洞察1", "洞察2", "洞察3"],
    "host_position": "你的核心立场（1-2句话，有立场、可被反驳、不骑墙）",
    "closing_question": "留给观众的思考题——需要想3秒才有答案的那种"
  },
  "segments": [
    {
      "segment_type": "opening",
      "audio_text": "完整配音文案",
      "script_segments": ["分段1", "分段2"],
      "estimated_duration": 20,
      "emotion": "curious",
      "cues": [{"text": "短句1", "start_time": 0, "end_time": 5}],
      "scene_elements": [
        {"element_type": "hook_card", "start_time": 0, "end_time": 20, "props": {"headline": "", "subtext": ""}}
      ],
      "meta": {}
    }
  ]
}
```

以上仅展示 opening 作为格式参考，你需要输出全部 7 种 segment_type。

### segments 各段要求

| type | 时长 | emotion | scene_elements | 要点 |
|------|------|---------|----------------|------|
| opening | 18-22s | curious | hook_card | 反常识钩子开场。不用"大家好欢迎来到"，直接给最有冲击力的点。hook_card 的 headline 是核心悬念，subtext 是补充信息 |
| context | 25-35s | analytical | story_header, info_table | 事件背景 + 核心数据。让观众建立认知基线。story_header 展示帖子标题/分数/评论数。audio_text ≥ 120 中文字 |
| viewpoint_a | 35-45s | engaged | comment_card, comment_bubble | 阵营一的完整展开。核心论点 + 代表评论原文/译文。不要只复述评论，要点出这个立场背后假设是什么。audio_text ≥ 150 中文字 |
| viewpoint_b | 35-45s | engaged | comment_card, comment_bubble | 阵营二的反驳 + 代表评论。指出与阵营一的核心分歧点。audio_text ≥ 150 中文字 |
| comment_deep | 50-65s | curious | comment_card × 2-3, perspective_compare | 不站主流阵营的"第三视角"评论。可能是内部人视角、跨领域类比、或者一条特别尖锐的质疑。这是最有信息增量的一段。每条评论配你的注脚——"为什么这个视角值得看"。audio_text ≥ 200 中文字 |
| synthesis | 25-35s | analytical | synthesis_card | 你的洞察提炼。不是复述各阵营观点，而是点出更深层的东西——这件事意味着什么，背后是什么趋势，对观众有什么影响。3-4个点。audio_text ≥ 120 中文字 |
| closing | 15-20s | warm | closing_card | 你的核心立场 + 思考题。不留"感谢收看"，留一个问题让观众在评论区争。思考题要有具体场景或动作，让观众能代入。audio_text ≥ 60 中文字 |

### script_segments 分段规则

- 每段 15-25 个中文字符，在自然断点处断开
- opening ~3-4 段, context ~4-6 段, viewpoint_a ~5-7 段, viewpoint_b ~5-7 段, comment_deep ~7-10 段, synthesis ~4-6 段, closing ~2-3 段
- 分段拼接后与 audio_text 内容一致

### scene_elements props 要求

- `hook_card`: `{"headline": "核心悬念/反常识结论", "subtext": "补充信息"}`
- `story_header`: `{"story_index": N}` - 帖子标题/分数/评论数将从原始数据自动填充
- `info_table`: `{"rows": [{"label": "标签", "value": "值"}]}` - 核心数据展示
- `comment_card`: `{"story_index": N, "comment_index": M}` - 自动填充
- `comment_bubble`: `{"story_index": N, "comment_index": M}` - 自动填充
- `perspective_compare`: `{"perspective_a": {"story_index": N, "comment_index": M}, "perspective_b": {"story_index": N, "comment_index": M}}` - 对照展示
- `synthesis_card`: `{"points": ["洞察1", "洞察2", "洞察3"]}` - 完整文本
- `closing_card`: `{"question": "", "visual_mood": ""}` - 完整文本
- `image_card`: `{"story_index": N, "image_index": M, "caption": "图片说明"}` - 展示文章配图，适合在 context 和 viewpoint 段使用

### cues 要求

- 将 audio_text 拆分为15-25字短句，每句一条 cue
- start_time/end_time 覆盖 0 到 estimated_duration，无间隙

## 约束

1. 只输出 JSON
2. 总时长 4-6 分钟
3. 只讲一个话题——把这个话题讲透，不讲其他
4. 翻译准确自然，技术术语保留英文或给标准译名
5. **viewpoint_camps 必须包含 2 个阵营**——不能只有一个视角
6. **selected_comments 必须包含至少 1 条非主流视角**——不是正方反方之外，是跟这个争论不在一个维度上的视角
7. **每条 selected_comment 的 why_notable 必须有**——不是"这条评论总结了X"，而是"这个视角独特在Y"
8. **synthesis 是核心壁垒**——不能是"双方都有道理"，而是"这件事告诉我们的更深层的东西是..."
9. **host_position 必须可被反驳**——如果你的立场没人会反对，那就太安全了
10. opening 不介绍日期，直接给钩子
11. 做减法：宁可少说一句，不要多说一句废话
12. comment_deep 段是整个节目的高潮——花最多时间在非典型视角上，这是观众转发的原因
13. 当故事有图片时（has_images=true），在 context 段中添加 1 个 image_card 场景元素，展示最能说明文章内容的图片

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
