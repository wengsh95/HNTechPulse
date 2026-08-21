# HN TechPulse 卡片模板说明

`tmp/template` 包含四个静态 HTML 卡片模板和一套共享设计系统。它们用于视觉预览、静态导出和与 Remotion 组件对齐风格，不是生产视频渲染入口。

## 文件结构

```text
tmp/template/
├── design/
│   ├── tokens.css       # 颜色、字体、字号、间距、圆角、阴影、动效与画布尺寸
│   ├── components.css   # 卡片、页眉、列表、指标、标签、引用、图文布局等组件
│   ├── animations.css   # 确定性入场动画与 stagger 工具类
│   └── render.js        # 直接打开 HTML 时使用的轻量 Mustache 渲染器
├── openingcard.html     # 开场卡：标题 + 3 条头条
├── eventcard.html       # 事件卡：单个故事详情 + 右侧图片
├── atmospherecard.html  # 氛围卡：立场分布 + 讨论焦点 + 评论金句
├── closingcard.html     # 收尾卡：今日 3 故事 + 核心变化
├── index.html           # 四张卡片的 iframe 预览页
└── TEMPLATE.md
```

## 打开方式

直接双击 `index.html` 或任一卡片 HTML 即可预览。每张卡底部都有：

```html
<script id="sample-data" type="application/json">...</script>
<script src="design/render.js"></script>
```

浏览器会读取 sample data，用轻量 Mustache 渲染器替换 `.card` 中的变量。用于 Python 渲染时，这些 script 标签只是模板文本；如果要导出纯静态 HTML，可以在渲染后移除它们。

## 统一风格原则

1. 所有视觉决策优先放在 `design/tokens.css`，包括 HN 橙、暖白纸面、字号、间距和底部字幕安全区。
2. 四张卡共享同一套页眉结构：`brand-strip`、`.card-title`、`.card-deck`。
3. 共享组件放在 `design/components.css`，例如 `.metric-pill`、`.tag`、`.quote`、`.news-item`、`.story`、`.panel`。
4. 单卡差异只体现在语义结构上：开场是新闻列表，事件是图文分栏，氛围是面板网格，收尾是回顾列表。
5. 动画保持确定性：固定时长、固定次数、`animation-fill-mode: both`，便于视频时间轴 seek。

## 模板变量

### `openingcard.html`

| 变量 | 类型 | 说明 |
| --- | --- | --- |
| `{{ date }}` | string | 日期，例如 `2026年6月7日` |
| `{{ subtitle }}` | string | 开场副标题 |
| `{{#stories}}...{{/stories}}` | list | 固定 3 条头条 |

`stories` 字段：`rank`、`title`、`subtitle`、`score`、`comments`。

### `eventcard.html`

| 变量 | 类型 | 说明 |
| --- | --- | --- |
| `{{ date }}` | string | 日期 |
| `{{ title }}` | string | 中文大标题 |
| `{{ source_name }}` | string | 来源标题或站点名 |
| `{{ source_url }}` | string | 来源 URL 或域名 |
| `{{ score }}` | int | HN points |
| `{{ comments }}` | int | 评论数 |
| `{{ why_watch }}` | string | “为何关注”段落 |
| `{{ impact }}` | string | “影响分析”段落 |
| `{{ image_url }}` | string | 右侧配图 |
| `{{ slide_index }}` / `{{ slide_total }}` | int | 页码 |
| `{{#tags}}...{{/tags}}` | list | 标签，字符串列表使用 `{{tags}}` |

### `atmospherecard.html`

| 变量 | 类型 | 说明 |
| --- | --- | --- |
| `{{ date }}` | string | 日期 |
| `{{ dispute_score }}` | string | 争议指数，例如 `3.7` |
| `{{ dispute_label }}` | string | 争议标签 |
| `{{ subtitle }}` | string | 副标题 |
| `{{ slide_index }}` / `{{ slide_total }}` | int | 页码 |
| `{{ support }}` / `{{ neutral }}` / `{{ skeptical }}` | int | 立场百分比，0-100 |
| `{{ conclusion }}` | string | 底部结论 |
| `{{#focus_items}}...{{/focus_items}}` | list | 讨论焦点，字符串列表使用 `{{focus_items}}` |
| `{{#quotes}}...{{/quotes}}` | list | 评论金句，字符串列表使用 `{{quotes}}` |
| `{{#tags}}...{{/tags}}` | list | 标签，字符串列表使用 `{{tags}}` |

### `closingcard.html`

| 变量 | 类型 | 说明 |
| --- | --- | --- |
| `{{ date }}` | string | 日期 |
| `{{ title }}` | string | 收尾标题 |
| `{{ subtitle }}` | string | 收尾副标题 |
| `{{#stories}}...{{/stories}}` | list | 今日回顾列表 |

`stories` 字段：`rank`、`zh`、`en`。

## Python 渲染示例

```python
import chevron

with open("tmp/template/openingcard.html", encoding="utf-8") as f:
    template = f.read()

data = {
    "date": "2026年6月7日",
    "subtitle": "AI 时代的快讯 / 洞察 / 趋势",
    "stories": [
        {"rank": 1, "title": "...", "subtitle": "...", "score": 1370, "comments": 472},
        {"rank": 2, "title": "...", "subtitle": "...", "score": 424, "comments": 151},
        {"rank": 3, "title": "...", "subtitle": "...", "score": 231, "comments": 426},
    ],
}

html = chevron.render(template, data)
```

注意：模板语法是 Mustache，不是 Jinja2。
