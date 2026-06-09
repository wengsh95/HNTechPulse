# 视频开场 / 收尾文案

本文档约束 `templates.py` 里 rule-based 生成的展示层文案，不直接调用 LLM。

目标：开场和结尾要适合 B 站发布。它们应该像成熟科技内容账号的口播，不是“今日信号”式内部标签，也不是机械串标题。

## 适用字段

- `generate_fixed_opening.audio_text`
- `cover_card.props.subtitle`
- `generate_fixed_closing.audio_text`
- `closing_card.props.summary_items / takeaways`

## 规则

### cover_card.subtitle

- 从 `highlight_entries[:3].editor_angle / signal / title_translation` 生成三个看点短语。
- 用 ` · ` 拼接，优先保留完整短语。
- 每个短语 6-14 字，整行不超过 50 字。
- 过长时删尾部钩子，不加省略号，不截半个词。
- 不写“今日信号”“今日三件事”这类栏目内部词。

### opening audio_text

- 2 句，35-65 字，适合 6-9 秒口播。
- 格式建议：
  - “早上好，这里是HN每日观察。”
  - “今天看 X、Y 和 Z，主线是……。”
- 开场必须直接告诉观众今天看什么；不要先讲宏大判断。
- 三个钩子要完整、可听懂，不硬截字段。
- 不要“本期视频将带你了解”“今天我们来聊聊”。

### closing audio_text

- 2 句，45-75 字，适合 8-12 秒口播。
- 第一句收束共同主线，不复读开场。
- 第二句给一个具体评论区问题或关注点，但问题应覆盖当天主线，避免只问第一条新闻。
- 可以自然引导关注，但不要“点赞投币三连”。
- 不使用“今天的主线是”这类开场框架词。

### closing_card

- 内容侧只提供 `summary_items / takeaways / keywords / totals`。
- 不生成 `signal_label`，不使用“今日信号”。
- `summary_items.title` 要像复盘标题，不像长句摘要。
- `takeaways` 应是行动/判断层面的短句，不是空泛升华。

## 风格

- 圈内表达，但不炫技。
- 不解释主流公司、产品、模型名。
- 不用空泛升华，不留废话。
- 中英文混排保持紧凑。
