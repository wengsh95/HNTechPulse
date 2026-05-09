# Roadmap

## Phase 1: Bug 修复

- [ ] **底部进度条** — 视频底部全宽进度条，显示当前 story 在全部 story 中的位置。涉及：新建 `ProgressBar.tsx` 组件，`HNTechPulseComposition.tsx` 中引入，根据当前帧/总帧计算进度。

## Phase 2: 评论分析管线

> 后续三段式展示、词云等功能的基础依赖。

- [ ] **独立 `analyze` 管线步骤** — 在 `enrich` 和 `script` 之间插入，对每条评论做 VADER 情感分析 + 启发式质量评分 + TF-IDF 关键词提取。结果缓存到 `data/{date}/comment_analysis.json`。
  - **数据模型**：`ContentComment` 扩展 `sentiment` (float, -1~+1)、`quality_score` (float, 0~1)、`keywords` (list[str])；`ContentItem` 扩展 `comment_word_freq` (dict[str, float])。
  - **情感**：VADER compound score，零 API 成本，对 HN 短文本/符号写法友好。
  - **关键词**：每个 story 内独立 TF-IDF，用 `scikit-learn` TfidfVectorizer，停用词过滤 + 技术术语保留。
  - **词频加权**：`comment_word_freq` 中每词的频次按评论 `quality_score` 加权，低质量评论的词自然被压低。
  - **依赖**：`vaderSentiment`、`scikit-learn`。
  - **配置**：`config.yaml` 新增 `analyze` 块（enabled, min_quality_score, max_keywords_per_comment, stopwords）。
- [ ] **评论质量评分** — 启发式综合分，用于过滤低质量评论和加权词频。信号来源：
  - **HN upvotes**：HN API 已有字段，当前 `ContentComment.upvotes` 存在但未采集，需在 `hn_fetcher.py` 中补充抓取。
  - **文本长度**：太短（<20字）通常无价值，太长可能跑题，中等最佳，钟形曲线打分。
  - **含代码块/链接**：正则匹配 `` ` `` / ``` / `http`，有则加分（信息密度高）。
  - **嵌套深度**：抓取时已有 depth 信息，深层回复多为争吵，逐层衰减。
  - **作者可信度**（可选）：需额外 API 查用户 karma，成本较高，优先级低。
- [ ] **评论数据送入 LLM** — 当前 `script_writer.py` 传 `comments_data=None`，评论完全未参与脚本生成。分析完成后，按 quality_score 排序取 top-N 高质量评论传给 LLM，替代当前无差别的截断方式。

## Phase 3: Prompt 优化

- [ ] **Prompt 进一步拆分** — 当前按 story 拆分已实现，但单 story prompt 仍较复杂。可拆为：R1a 标题翻译 + R1b 评论分析 + R1c 立场提取，允许多次独立 LLM 请求，降低单次 token 压力和 JSON 解析失败率。
- [ ] **每条评论单独 LLM 分析** — 当前评论按 story 批量送入 LLM。改为逐条评论独立请求：情感分析 + 中文翻译 + 质量评分。需考虑 API 成本和并发控制。

## Phase 4: Story 三段式展示

> 依赖 Phase 2 评论分析管线。
>
> 每个 story 从当前的单段速览改为三段递进结构：**事件 → 氛围 → 社区原声**。
> 四个舆情核心指标（争议度、情感细分、关键词、高质量评论）按信息密度递进分布到三段中。

### 布局

```
┌─────────────────────────────────────────────────┐
│  第一段：事件 (5s)                               │
│                                                 │
│  ┌───────────────────────────────────────────┐  │
│  │  [AI] OpenAI releases o3                  │  │
│  │                                           │  │
│  │  一句话摘要...                             │  │
│  │                                           │  │
│  │                              ┌──────────┐ │  │
│  │                              │ 争议度 8.2│ │  │
│  │                              └──────────┘ │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│  第二段：氛围 (5s)                               │
│                                                 │
│  ┌─────────┐  ┌─────────────────────────────┐  │
│  │  饼图    │  │  [隐私] [推理] [成本]       │  │
│  │ 支持 30% │  │  [AGI]  [benchmark]         │  │
│  │ 质疑 40% │  │                             │  │
│  │ 担忧 20% │  │  关键词/议题标签             │  │
│  │ 调侃 10% │  │  (按词频着色,按情感加边框)   │  │
│  └─────────┘  └─────────────────────────────┘  │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│  第三段：社区原声 (8-10s)                        │
│                                                 │
│  ┌───────────────────────────────────────────┐  │
│  │ [质疑] "The benchmark cherry-picks        │  │
│  │         tasks that favor chain-of-thought" │  │
│  │         — user_abc                        │  │
│  └───────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────┐  │
│  │ [担忧] "This pricing makes it unusable    │  │
│  │         for any real production workload"  │  │
│  │         — user_xyz                        │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

### 各段详情

- [ ] **第一段：事件简述 + 争议度** — LLM 生成事件摘要，画面展示标题 + 配图。标题旁显示争议度徽章（`descendants / score`，归一化 0-10，颜色：绿=共识→黄=有分歧→红=高争议）。时长 ~5s。
- [ ] **第二段：社区氛围** — 左侧情感饼图（`stance_distribution` 五分类，已有数据），右侧关键词/议题标签（来自 `comment_word_freq`，按词频着色大小、按情感加边框色）。时长 ~5s。
- [ ] **第三段：社区原声** — 取 `quality_score` top-2 高质量评论，直接引用原文（`quote` 字段），保留作者名 + stance 标签。让社区自己说话，比 LLM 总结更有说服力。时长 ~8-10s。
- [ ] **时长与数量平衡** — 三段式后每个 story ~20s，10 个 story ~200s，加 opening/dashboard/closing 总时长约 4-5 分钟（当前约 2-3 分钟）。需决定：保持 10 个 story 接受更长视频，还是减少到 5-6 个 story 换取深度。

### 数据流

```
hn_fetcher          → score, descendants (已有)
                      ↓
analyze (Phase 2)   → sentiment, quality_score, keywords (规划中)
                      ↓
script_writer       → controversy_score = descendants / score (一行计算)
                      → top_keywords (从 analyze 结果取)
                      → top_comments (按 quality_score 排序取 top-2)
                      ↓
remotion_props      → 传入三段各自的 props
                      ↓
Remotion            → 事件卡(标题+争议度) → 氛围卡(饼图+标签) → 原声卡(评论引用)
```

## Phase 5: 视觉效果

- [ ] **视频配图 — 独立 ImageCard 插入时间线** — 每个 story 在 `story_scan_card` **之前**插入 2-3 秒的 `image_card`，"图先入，话跟上"节奏。图片按优先级降级链获取：
  1. **原文配图**（已有）：enricher 的 `_extract_images()` 抓取 `og:image` / `twitter:image` / `<article>` 内图片，存入 `ContentItem.article_images`。
  2. **公司 Logo**（新增）：从文章 URL 域名拼接 Clearbit Logo API（`logo.clearbit.com/{domain}`），零配置免费，HN 热门故事多来自知名公司命中率高。Logo 为正方形小图，需带背景色/渐变容器撑满卡片。
  3. **网页截图**（新增）：enricher 的 headless Chrome 访问时顺手截 viewport（1280x720），命名 `{source_id}_screenshot.jpg`，存入 `data/{date}/images/`。
  4. **无配图**：以上均无则不插入 ImageCard，保持原节奏。
  - **涉及**：`article_enricher.py`（新增 Logo 下载 + 截图逻辑）、`script_writer.py`（生成 `image_card` scene_element + 调整 `estimated_duration`）、`ImageCard.tsx`（Logo 居中+背景容器样式）、`remotion_props.py`（序列化图片路径）、`config.yaml`（enrich 配置项）。
- [ ] **StoryScanCard 关键词标签** — LLM 输出 `keywords` 字段（如"AI虚假繁荣"、"隐私危机"），画面上用醒目的标签/徽章展示，帮助观众快速抓取信息。涉及：`single_story_scan.md` prompt、`remotion_props.py` expander、`Elements.tsx` StoryScanCard 组件。
- [ ] **词云** — 基于 `comment_word_freq` 生成词云。Python 端输出词频 JSON，Remotion 端用 `d3-cloud` 动态渲染（逐词飞入动画）。降级方案：`wordcloud` 库出静态 PNG。
- [ ] **动画小人 + 差分表情** — 左下角放置像素风/简笔画小人，每个 story 切换时显示一句话评价 + 对应表情（惊讶/思考/赞同/质疑等）。涉及：新建 `Character.tsx` 组件，多帧 sprite 或 SVG 差分，与 story 切换同步。
- [ ] **音效与转场** — 当前仅有 TTS 旁白，缺少：场景切换音效（whoosh/叮）、进度音效（tick）、强调音效（pop）。需在 Remotion 中引入 `<Audio>` 组件，准备音效素材。
- [ ] **Apple Keynote 风格** — 整体视觉向 Keynote 靠拢：大标题居中、极简卡片、Magic Move 式转场（元素变形过渡）、深色渐变背景、优雅的动画曲线。需重构组件样式和转场逻辑。

---

## 执行计划

### 第一批：1 周内（低风险高回报）

- [ ] **底部进度条**（Phase 1）— 0.5 天
- [ ] **视频配图**（Phase 5）— 2-3 天。基础设施已 90% 就绪（ImageCard.tsx + _expand_image_card() + article_images），只需 enricher 加 Logo/截图、script_writer 插入 element、ImageCard 加 Logo 容器样式。

### 第二批：2-3 周（核心管线升级）

- [ ] **评论分析管线**（Phase 2）— 5-7 天。新增 analyze 步骤 + 质量评分 + 评论送入 LLM。Phase 4 的前置依赖。
- [ ] **事件简述 + 争议度**（Phase 4 第一段）— 2-3 天。不依赖 Phase 2，可提前做。新建 EventCard.tsx，争议度 = descendants/score。

### 第三批：4-5 周（深度展示）

- [ ] **社区氛围 + 社区原声**（Phase 4 第二/三段）— 3-5 天。依赖 Phase 2 的 comment_word_freq 和 quality_score。
- [ ] **关键词标签**（Phase 5）— 1 天。依赖 Phase 2。
- [ ] **音效与转场**（Phase 5）— 1-2 天。
- [ ] **Prompt 拆分**（Phase 3）— 2-3 天。

### 暂缓（ROI 低或工程量大）

- 逐条评论 LLM 分析（Phase 3）— 200+ 次 LLM 调用，成本高
- 词云（Phase 5）— d3-cloud 动态渲染复杂
- 动画小人（Phase 5）— 需设计素材，5-7 天
- Apple Keynote 风格（Phase 5）— 等同重写 UI 层，5-7 天
