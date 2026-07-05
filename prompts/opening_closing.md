# 视频开场 / 收尾文案

本文档约束开场和结尾的生成规则。开场由 LLM 生成（`prompts/opening.md`），结尾由 rule-based 生成。

目标：开场和结尾要适合 B 站发布。它们应该像成熟科技内容账号的口播，不是"今日信号"式内部标签，也不是机械串标题。开场负责 3 秒留存，结尾负责把观众礼貌送走。

## 适用字段

- `generate_fixed_opening.audio_text`（LLM 生成）
- `cover_card.props.subtitle`（rule-based）
- `generate_fixed_closing.audio_text`（rule-based）
- `closing_card.props.summary_items / takeaways`（rule-based）

## 规则

### cover_card.subtitle

- 从 `highlight_entries[:2].editor_angle / signal / title_translation` 生成两个看点短语。
- 用 ` · ` 拼接，优先保留完整短语。
- 每个短语 6-14 字，整行不超过 50 字。
- 过长时删尾部钩子，不加省略号，不截半个词。
- 不写"今日信号""今日三件事"这类栏目内部词。

### opening audio_text

- 由 LLM 生成，参见 `prompts/opening.md`。
- 1 句，20-35 字，适合 3-5 秒口播。
- 第一目标是 3 秒留存：用反常识问题、冲突判断或共同主题进入。
- 如果没有传入具体 story 内容，不要提具体公司、产品、安全事故或 AI 写代码等事实。
- 不要模板化，不要固定句式。
- 可根据日期/节日/周末/月末自然调整语气。
- 避免“今天 HN 上都在聊什么”“一起看看”“本期带来三条新闻”。

### closing audio_text

- 2 句，40-70 字，适合 7-11 秒口播。
- 第一句收束共同主线，不复读开场。
- 第二句给一个温和问候或下期再见，不再抛评论区反问；问候可以结合节日、周末、月末、年末等日期语境。
- 可以自然引导关注，但不要“点赞投币三连”，也不要强运营口吻。
- 不使用“今天的主线是”这类开场框架词。
- 结尾可以包含当天至少一个具体对象、成本或场景，但必须是陈述句，不用反问。
- 结尾问候要克制，例如“今天就到这里，祝你今天顺利，我们下期继续。”
- 节日问候只在明确命中日期时使用，不要强行蹭热点；没有节日时优先用普通工作日/周末问候。

### closing_card

- 内容侧只提供 `summary_items / takeaways / keywords / totals`。
- 不生成 `signal_label`，不使用“今日信号”。
- `summary_items.title` 要像复盘标题，不像长句摘要。
- `takeaways` 应是行动/判断层面的短句，不是空泛升华。

## 风格

- 圈内表达，但不炫技。
- 不解释主流公司、产品、模型名。
- 不用空泛升华，不留废话。
- 整体克制，不阴阳怪气，不连续追问。
- 中英文混排保持紧凑。
