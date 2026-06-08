# 视频开场 / 收尾文案

本文件规范 opening 段和 closing 段中**展示层文案**的生成规则。展示层文案指观众在视频里看到/听到的引导性文字, 不包括具体故事内容 (故事内容由 `story_script.md` / `article_enrich.md` 生成).

## 适用场景

- `templates.py:generate_fixed_opening` 生成的 `audio_text` (开场旁白)
- `templates.py:generate_fixed_opening` 生成的 cover_card.props.subtitle (封面副标题)
- `templates.py:generate_fixed_closing` 生成的 `audio_text` (收尾旁白)
- `templates.py:generate_fixed_closing` 生成的 closing_card.props.summary_items / takeaways (收尾列表)

## 受众

延续 `persona.md` 的"圈内人"定位: HN / 技术 / 创投圈读者. 假设他们熟知主流公司/产品/模型名.

## 字段规则

### cover_card.subtitle (封面副标题)

**默认是日期**, 但**改成"今日 3 件事钩子"** (rule-based, 不调 LLM, 零成本):

1. 从 `highlight_entries[:3]` 里取 `editor_angle`
2. 用 ` · ` 拼接, 总长控制在 22-40 字
3. 超过 40 字就截断第 3 个并加 `…`
4. 例子:
   - `OpenAI联手AWS · Anthropic递表 · Alphabet 800亿`
   - `Anthropic 估值破 9000 亿 · 三大模型同日上新`
   - `云厂商卷价格 · 苹果造芯 · Cursor 推企业版`

**为什么不直接用 LLM 生成**: 钩子本质是数据, rule-based 已经够用, 调 LLM 是过度设计. 如果钩子质量后续不够, 再升级到 LLM.

### opening audio_text (开场旁白)

**当前硬编码**: `早上好，这里是 HN每日观察，带你看昨天HN发生了什么。`

**升级方向** (待实现):
- 风格: 1-2 句开场, 不啰嗦
- 模式 1 (默认): `早上好, HN每日观察。今天 3 条: [钩子前半句]`
  - 例: `早上好, HN每日观察。今天 3 条, 关键词: 800 亿、S-1、AWS。`
- 模式 2 (周一): 加入"新一周"修饰
  - 例: `新一周开始, HN每日观察, 今天 3 条: 800 亿、S-1、AWS。`
- 模式 3 (周五): 加入"周末"提示
  - 例: `周五了, HN每日观察。今天 3 条, 周末可以慢慢消化: 800 亿、S-1、AWS。`
- 总字数: 30-50 字, 配音 5-8s

### closing audio_text (收尾旁白)

**当前硬编码**: `今天的 HN 速览就到这里，我们明天继续看哪些讨论值得停一下。` (周一到周四) / `今天的 HN 速览就到这里，周末继续留意那些真正值得追的问题。` (周五周六)

**升级方向** (待实现):
- 保持现有 8s 时长
- 风格不变, 但允许每天略微变化 (基于今日 takeaway)
- 例: `今天的 3 件事: [takeaway 1]、[takeaway 2]、[takeaway 3]. 明天继续。`

### closing_card 标题

收尾卡不再生成 `signal_label`, 也不使用“今日信号”这类固定标题。
标题由 Remotion 模板层统一处理, 内容侧只提供 `summary_items` / `takeaways`。

## 实现方式

`templates.py` 里的 `generate_fixed_opening` 和 `generate_fixed_closing` 仍是主入口. 上述规则的实现优先级:

1. **P0**: cover_card.subtitle 改成"今日 3 件事钩子" (rule-based, 5 行代码) ← 立即做
2. **P1**: opening audio_text 改成"3 关键词开场" (rule-based, 5 行代码) ← 立即做
3. **P2**: closing audio_text / takeaways 改成动态 (LLM 调用, 较复杂) ← 后续

## 注意事项

- 所有文案**仍然要去圈外化**: 不展开解释"Anthropic 是谁""S-1 是什么"——HN 受众都懂
- 修辞词**慎用**: 偶尔一句"意料之外"作为记忆点 OK, 但 100% 干瘪口播和 100% 修辞腔都不可取
- 总字数严格控制, 因为是 60-130 秒视频, 不留 1 句废话
