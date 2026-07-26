# 小红书图文生产流程 · Social Card Workflow

HNTechPulse 默认产物：小红书深度卡片（3:4，1080×1440，固定 6 页）。
基于 2026-07-13 期「Claude Code 吞 token 黑箱」实战总结。

> 当前已自动化。第 1-4 节是选材与视觉原则；第 5 节保留为手工调版
> 备用流程。日常运行只需 `scripts/agent_run.py`。

## 何时用

每日直接运行：

```bash
uv run python scripts/agent_run.py --date YYYY-MM-DD
```

管线自动完成选题、抓图、社区立场分析、卡片规划和 PNG 渲染。

## 1. 选材判断

一期通常 3 条故事。**不要三条平铺做速览**——小红书不吃速览，吃深度。

判断标准：

| 信号 | 适合做深度 | 适合砍掉 |
|------|-----------|---------|
| 热度 | ▲ 高 + 💬 多 | ▲ 低 |
| 数字戏剧性 | 有对比数字（33k vs 7k） | 纯定性 |
| 社区分裂 | 有对立立场（质疑/支持） | 一边倒 |
| 受众共鸣 | 开发者/科技圈痛点 | 太宏观/太基建 |

**建议：挑 1 条最有张力的做 6 页深度，其余砍掉。** 聚焦比铺开更容易爆。

### 数据位置

```
data/{month}/{date}/
├── pipeline/
│   ├── content.json         # 新闻正文、摘要、角度、关键点
│   ├── comment_judgement.json  # 社区立场：四档（representative/counterpoint/detail/color）+ quote_candidates
├── media/images/            # HN 截图 + 源站配图（按 story_id 命名）
└── publish/
    ├── xhs_cards.json       # 单条焦点新闻 + 6 页结构化卡片契约
    └── xhs_cards/           # index.html、assets、6 张 PNG、总览图
```

关键提取：
- `content.json` -> `items[]`：标题、摘要、关键点和影响
- `comment_judgement.json` -> `stories.{id}.comment_lanes`：四档评论 + `claim` 字段是现成金句
- `comment_judgement.json` -> `stories.{id}.discussion_summary`：一句话争论总结
- `media/images/{story_id}_screenshot.jpg`：HN 原帖截图（最值钱的"不 AI 感"素材）

## 2. 调用 Skill

```
Skill: guizang-social-card-skill
```

这个 skill 会注入完整的图文生成规范：布局配方、配色系统、组件规格、验证器。

## 3. 选风格

两种风格，**同一故事两种讲法**：

| | Swiss 国际主义 | Editorial 杂志风 |
|--|--------------|----------------|
| 适合 | 数据驱动、发布说明、对比排名 | 立场之争、深度调查、叙事质疑 |
| 字体 | Inter 无衬线，极细大字 | Noto Serif SC 宋体 |
| 背景 | 纯色干净 | WebGL 墨流 + 纸纹颗粒 |
| 核心组件 | KPI 塔、横条图、矩阵 | callout 引语框、ledger 账本、marginalia 侧栏 |
| 配色 | safety-orange / ikb / lemon-* | ink-classic / forest-ink / kraft-paper / dune / indigo-porcelain |

**判断公式：数据用 Swiss 讲，质疑用 Editorial 讲。**

- 内容的核心张力是"数字对比" -> Swiss
- 内容的核心张力是"立场之争 / 大厂质疑" -> Editorial

## 4. 页面规划

小红书 3:4 图文，5-9 页。6 页是甜点。

### 通用 6 页骨架（可按内容微调）

```
P1  封面钩子    一句话 + 一个核心数字/截图，让人停下
P2  证据/对比   先亮证据（截图）或先立对比（数字），建立可信度
P3  拆解        把核心数字展开，讲清"为什么"
P4  争论立场    社区分裂的百分比 + 各派一句话主张
P5  争论金句    各派最高分原话（callout 放大），制造评论区冲突
P6  落点        精简总结 + 一个挑逗性问题引导评论
```

### 叙事线选择

两种排序，看内容定：

- **先证据后拆解**（推荐用于质疑型）：钩子 -> 证据截图 -> 拆解数字 -> 争论 -> 落点
- **先对比后证据**（推荐用于数据型）：钩子 -> 数字对比 -> 成本拆解 -> 证据 -> 落点

### 文案原则

- **标题 ≠ B 站标题**。B 站是「【HN日报】Claude Code空载先吞33k token」，小红书要更个人、更挑逗：「还没读你的话，先吞了三万」
- **金句用原话**。`comment_judgement.json` 的 `claim` 字段是现成的社区原话，直接进 callout，比自己编更有"真人在吵"的感觉
- **落点提问要短**。"底包成标配，你选订阅还是按量？" 比 "按月订阅还是按上下文计费更合理？" 更锐
- **每页一个观点**。不要塞，塞满反而像 PPT

## 5. 手工调版备用流程

### 5.1 建任务目录

```bash
mkdir -p social-card-{slug}/assets social-card-{slug}/output
```

复制素材：

```bash
cp data/{month}/{date}/media/images/{story_id}_screenshot.jpg social-card-{slug}/assets/hn-screenshot.jpg
cp data/{month}/{date}/media/images/{story_id}_0.jpg social-card-{slug}/assets/story-thumb.jpg
```

记录来源到 `assets/SOURCES.md`（管线自带素材，非外部图库，无需第三方署名）。

### 5.2 复制 seed 模板

```bash
# Swiss
cp ~/.agents/skills/guizang-social-card/assets/template-swiss-card.html social-card-{slug}/index.html
# Editorial
cp ~/.agents/skills/guizang-social-card/assets/template-editorial-card.html social-card-{slug}/index.html
# Editorial 还需要 WebGL 背景脚本
cp ~/.agents/skills/guizang-social-card/assets/magazine-bg-webgl.js social-card-{slug}/assets/
```

### 5.3 设配色

改 `<html>` 标签一个属性：

```html
<!-- Swiss -->
<html lang="zh-CN" data-accent="safety-orange">
<!-- Editorial -->
<html lang="zh-CN" data-theme="forest-ink">
```

### 5.4 编写 HTML

替换 `<!-- POSTERS_HERE -->` 后的占位 poster，每页一个 `<section class="poster xhs">`。

布局配方见 skill 的 `references/layout-recipes.md`：
- Swiss: S01 封面 / S09 KPI 塔 / S10 横条图 / S04 浏览器框 / S07 账本 / S12 矩阵
- Editorial: M01 封面 / M03 分栏 / M08 账本 / M10 证据 / M11 侧栏 / M07 结尾

关键规则：
- 每页只选一个 recipe，不要混
- `card-ink` / `card-accent` / `card-fill` / `card-outlined` 互斥，同一节点只用一个
- Swiss: "the larger, the lighter" —— 大字用 weight 200，不要 inline font-weight
- Editorial: 不要用纯色平铺背景，必须有 WebGL 墨流 + grain 层

### 5.5 渲染

```bash
uv run python social-card-{slug}/render.py
```

渲染脚本（Playwright Python，用项目 venv）：

```python
# render.py - 放在任务目录根
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
HTML = HERE / "index.html"
OUT = HERE / "output"
OUT.mkdir(exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path=str(
            Path.home()
            / "AppData/Local/ms-playwright/chromium-1224/chrome-win64/chrome.exe"
        ),
        args=["--no-sandbox"],
    )
    page = browser.new_page(viewport={"width": 1080, "height": 1440})
    page.goto(HTML.as_uri(), wait_until="networkidle")
    page.wait_for_timeout(900)
    page.evaluate(
        """() => {
            if (window.lucide && typeof window.lucide.createIcons === 'function') {
                window.lucide.createIcons();
            }
        }"""
    )
    page.wait_for_timeout(500)

    ids = page.eval_on_selector_all(
        ".poster.xhs", "els => els.map(e => e.id || 'unknown')"
    )
    for pid in ids:
        el = page.query_selector(f"#{pid}")
        if not el:
            continue
        el.screenshot(path=str(OUT / f"{pid}.png"))
    browser.close()
```

> **环境注意**：Playwright 的 headless-shell 没装，用 `executable_path` 指向
> `chromium-1224/chrome-win64/chrome.exe`（完整 Chromium，非 headless）。
> 如果后续装了 `playwright install chromium`，可以去掉 `executable_path`。

### 5.6 验证

```bash
# 需要在任务目录下有 node_modules/playwright（npm install playwright）
cd social-card-{slug}
node ~/.agents/skills/guizang-social-card/validate-social-deck.mjs . --style=swiss
# 或 --style=editorial
```

验证器规则：
- R1 溢出（FAIL）—— 内容超出 1440px
- R2 footer 碰撞（FAIL）—— 内容压到底部 issue-strip
- R3 Swiss 字重（FAIL）—— 大字不能 ≥600
- R4 最小字号（FAIL）—— 低于移动端可读底线
- R5 密度（WARN）—— 3:4 画布填充 <75%
- R6 标题行数（FAIL）—— h-xl 超出行数上限
- R7 figure 边距漂移（FAIL）

**FAIL 必须修，WARN 视情况**。封面页 R5 低密度通常是设计留白，可接受。

### 常见修复

| 问题 | 修复 |
|------|------|
| R1 溢出 | 减小 gap / padding / 字号，或砍一行内容 |
| R2 footer 碰撞 | `.content` 加 `padding-bottom:130-170px`（issue-strip 在 bottom:56px） |
| R5 密度低 | 加内容行、加 callout、把单句扩成段落；封面可接受低密度 |
| R6 标题超行 | 换断句位置或缩字数，不要缩字号 |

### 5.7 出总览图

```bash
uv run python -c "
from PIL import Image
import os
d='social-card-{slug}/output'
files=sorted(f for f in os.listdir(d) if f.endswith('.png') and not f.startswith('_'))
ims=[Image.open(os.path.join(d,f)) for f in files]
w,h=ims[0].size
cols,rows,pad=3,2,24
sheet=Image.new('RGB',(cols*w+(cols+1)*pad,rows*h+(rows+1)*pad),'#1a1a1a')
for i,im in enumerate(ims):
    r,c=divmod(i,cols)
    sheet.paste(im,(pad+c*(w+pad),pad+r*(h+pad)))
sheet.save('social-card-{slug}/output/_contact-sheet.png')
"
```

## 6. 交付

成品在 `social-card-{slug}/output/`：
- `xhs-01.png` ~ `xhs-06.png`：6 张 1080×1440
- `_contact-sheet.png`：3×2 总览图

## 快速复用清单

下次做新一期：

1. `uv run python scripts/agent_run.py --date YYYY-MM-DD`
2. `uv run python scripts/agent_status.py --date YYYY-MM-DD`
3. 查看 `publish/xhs_cards/_contact-sheet.png`
4. 仅改排版时运行 `--steps render_xhs_cards`，无需再次调用 LLM
5. 输入变化时运行 `--steps plan_xhs_cards,render_xhs_cards`

## 已有产出

| 日期 | 故事 | 目录 | 风格 | 配色 |
|------|------|------|------|------|
| 2026-07-13 | Claude Code 吞 33k token | `social-card-claude-token/` | Swiss | safety-orange |
| 2026-07-13 | Claude Code 吞 33k token | `social-card-claude-token-editorial/` | Editorial | forest-ink |

同一期做了两版对比：Swiss 橙（数据快）vs Editorial 墨绿（深度调查）。
Editorial 版验证器全绿（0 FAIL 0 WARN），结构针对"质疑"故事调过。
