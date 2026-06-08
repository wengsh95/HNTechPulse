# 视频开场 / 收尾文案

本文件约束 `templates.py` 里 rule-based 生成的展示层文案，不直接调用 LLM。

## 适用字段

- `generate_fixed_opening.audio_text`
- `cover_card.props.subtitle`
- `generate_fixed_closing.audio_text`
- `closing_card.props.summary_items / takeaways`

## 规则

### cover_card.subtitle

- 用 `highlight_entries[:3].editor_angle` 生成“今日 3 件事钩子”。
- 用 ` · ` 拼接，优先保留完整短语。
- 过长时删除尾部钩子，不加省略号，不截半截词。

### opening audio_text

- 1-2 句，30-50 字，5-8 秒。
- 格式：`早上好，这里是HN每日观察。{今日主线}今天看{三个完整短钩子}。`
- 钩子宁可回退到关键词，也不能硬截字段。

### closing audio_text

- 8-12 秒，基于今日 takeaway。
- 不复用“今天的主线是”这类开场框架。
- 可以加一个具体问题，引导评论区。

### closing_card

- 内容侧只提供 `summary_items / takeaways / keywords / totals`。
- 不生成 `signal_label`，不使用“今日信号”。

## 风格

- 圈内人表达，不解释主流公司、产品、模型名。
- 不用空泛升华，不留废话。
- 中英文混排保持紧凑。
