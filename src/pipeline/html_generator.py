import html as html_mod
from pathlib import Path

from src.core.models import ContentPackage, Script
from src.utils.logger import setup_logger


class HtmlGenerator:
    def __init__(self, debug: bool = False, level=None):
        self.logger = setup_logger(__name__, debug=debug, level=level)

    def generate(self, content: ContentPackage, script: Script, date: str) -> None:
        parts: list[str] = []

        parts.append("<!DOCTYPE html>")
        parts.append('<html lang="zh-CN">')
        parts.append("<head>")
        parts.append(f"<title>HN TechPulse | {date}</title>")
        parts.append('<meta charset="utf-8">')
        parts.append(
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
        )
        parts.append('<link rel="preconnect" href="https://fonts.googleapis.com">')
        parts.append(
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        )
        parts.append(
            '<link href="https://fonts.googleapis.com/css2?family=Anthropic+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,500;0,8..60,600;1,8..60,400&display=swap" rel="stylesheet">'
        )
        parts.append("<style>")
        parts.append(self._css())
        parts.append("</style>")
        parts.append("</head>")
        parts.append("<body>")

        # ── Header ──
        parts.append('<header class="site-header">')
        parts.append('  <div class="header-accent-bar"></div>')
        parts.append('  <div class="header-inner">')
        parts.append(
            '    <div class="brand">HN<span class="brand-accent">TechPulse</span></div>'
        )
        parts.append(f'    <div class="header-date">{date}</div>')
        parts.append("  </div>")
        parts.append("</header>")

        # ── Stats bar ──
        total_stories = len(content.items)
        total_score = sum(item.score or 0 for item in content.items)
        total_comments = sum(item.comment_count or 0 for item in content.items)
        categories: dict[str, int] = {}
        for item in content.items:
            cat = item.category or "未分类"
            categories[cat] = categories.get(cat, 0) + 1

        parts.append('<div class="stats-bar">')
        parts.append(
            f'  <div class="stat"><span class="stat-value">{total_stories}</span><span class="stat-label">故事</span></div>'
        )
        parts.append(
            f'  <div class="stat"><span class="stat-value">{total_score:,}</span><span class="stat-label">总分数</span></div>'
        )
        parts.append(
            f'  <div class="stat"><span class="stat-value">{total_comments:,}</span><span class="stat-label">总评论</span></div>'
        )
        parts.append(
            f'  <div class="stat"><span class="stat-value">{len(categories)}</span><span class="stat-label">分类</span></div>'
        )
        parts.append("</div>")

        # ── Category pills ──
        parts.append('<div class="category-bar">')
        for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
            parts.append(
                f'  <span class="category-pill">{html_mod.escape(cat)} <em>{count}</em></span>'
            )
        parts.append("</div>")

        # ── Story table ──
        parts.append('<section class="section">')
        parts.append('  <h2 class="section-title">故事列表</h2>')
        parts.append('  <div class="table-wrap">')
        parts.append("    <table>")
        parts.append(
            "      <thead><tr><th>#</th><th>标题</th><th>分数</th><th>评论</th><th>分类</th></tr></thead>"
        )
        parts.append("      <tbody>")
        for i, item in enumerate(content.items, 1):
            title = html_mod.escape(item.title_cn or item.title or "")
            score = item.score if item.score is not None else "-"
            comments = item.comment_count if item.comment_count is not None else "-"
            category = html_mod.escape(item.category or "-")
            score_display = (
                f'<span class="score-hot">{score}</span>'
                if isinstance(score, int) and score >= 500
                else str(score)
            )
            parts.append(
                f'        <tr><td class="row-num">{i}</td><td class="row-title">{title}</td><td>{score_display}</td><td>{comments}</td><td><span class="td-cat">{category}</span></td></tr>'
            )
        parts.append("      </tbody>")
        parts.append("    </table>")
        parts.append("  </div>")
        parts.append("</section>")

        # ── Story details ──
        parts.append('<section class="section">')
        parts.append('  <h2 class="section-title">故事详情</h2>')
        for i, item in enumerate(content.items, 1):
            title = html_mod.escape(item.title_cn or item.title or "")
            category = html_mod.escape(item.category or "")
            score = item.score or 0
            comment_count = item.comment_count or 0

            parts.append('  <article class="story-card">')
            parts.append('    <div class="story-header">')
            parts.append(f'      <span class="story-index">{i:02d}</span>')
            parts.append('      <div class="story-title-group">')
            parts.append(f'        <h3 class="story-title">{title}</h3>')
            parts.append('        <div class="story-meta">')
            if category:
                parts.append(f'          <span class="meta-cat">{category}</span>')
            parts.append(f'          <span class="meta-score">{score} pts</span>')
            parts.append(
                f'          <span class="meta-comments">{comment_count} comments</span>'
            )
            parts.append("        </div>")
            parts.append("      </div>")
            parts.append("    </div>")

            parts.append('    <div class="story-body">')

            if item.url:
                url_escaped = html_mod.escape(item.url)
                display_url = (
                    url_escaped[:60] + "..." if len(url_escaped) > 60 else url_escaped
                )
                parts.append(
                    f'      <div class="story-link"><a href="{url_escaped}" target="_blank" rel="noopener">{display_url}</a></div>'
                )

            if item.editor_angle:
                parts.append(
                    f'      <div class="field"><span class="field-label">编辑视角</span>{html_mod.escape(item.editor_angle)}</div>'
                )

            if item.why_it_matters:
                parts.append(
                    f'      <div class="field field-important"><span class="field-label">为什么重要</span>{html_mod.escape(item.why_it_matters)}</div>'
                )

            if item.key_points:
                parts.append(
                    '      <div class="field"><span class="field-label">要点</span><ul class="key-points">'
                )
                for kp in item.key_points:
                    point_text = kp.get("point", "") or kp.get("text", "")
                    if point_text:
                        parts.append(f"        <li>{html_mod.escape(point_text)}</li>")
                parts.append("      </ul></div>")

            if item.article_summary:
                parts.append(
                    f'      <div class="field"><span class="field-label">摘要</span><p class="summary-text">{html_mod.escape(item.article_summary)}</p></div>'
                )

            if item.keywords:
                parts.append('      <div class="keywords">')
                for kw in item.keywords:
                    parts.append(
                        f'        <span class="keyword">{html_mod.escape(kw)}</span>'
                    )
                parts.append("      </div>")

            # Top comments
            if item.comments:
                top_comments = sorted(
                    item.comments,
                    key=lambda c: (c.quality_score or 0, c.upvotes or 0),
                    reverse=True,
                )[:3]
                if top_comments:
                    parts.append('      <div class="comments-section">')
                    parts.append('        <div class="comments-header">精选评论</div>')
                    for c in top_comments:
                        author = html_mod.escape(c.author or "anonymous")
                        body = html_mod.escape((c.content_cn or c.content or "")[:200])
                        upvotes = c.upvotes or 0
                        parts.append(
                            f'        <div class="comment"><div class="comment-author">{author}<span class="comment-votes">{upvotes}</span></div><div class="comment-body">{body}</div></div>'
                        )
                    parts.append("      </div>")

            parts.append("    </div>")
            parts.append("  </article>")

        parts.append("</section>")

        # ── Script overview ──
        if script and script.segments:
            parts.append('<section class="section">')
            parts.append('  <h2 class="section-title">脚本概览</h2>')
            total_duration = sum(seg.duration for seg in script.segments)
            parts.append(
                f'  <div class="script-meta">总时长 {total_duration:.1f}s / {len(script.segments)} 段</div>'
            )
            for seg in script.segments:
                seg_type = html_mod.escape(seg.segment_type)
                duration = seg.duration
                text = html_mod.escape(seg.audio_text.strip())
                type_class = f"seg-type-{seg.segment_type}"
                parts.append(
                    f'  <div class="segment {type_class}"><div class="segment-header"><span class="seg-type">{seg_type}</span><span class="seg-duration">{duration:.1f}s</span></div><p class="segment-text">{text}</p></div>'
                )
            parts.append("</section>")

        # ── Footer ──
        parts.append('<footer class="site-footer">')
        parts.append(
            '  <div class="footer-inner">HN TechPulse &mdash; 每日技术社区速览</div>'
        )
        parts.append("</footer>")

        parts.append("</body></html>")

        output_path = Path(f"data/{date}/output.html")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(parts), encoding="utf-8")
        self.logger.info(f"HTML 已保存至 {output_path}")

    @staticmethod
    def _css() -> str:
        return """
/* ── Reset & Base ── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  /* Anthropic light palette — warm cream, dark text, terracotta accent */
  --bg-000: #ffffff;
  --bg-100: #faf8f5;
  --bg-200: #f5f2ed;
  --bg-300: #eeebe5;
  --bg-hover: #f0ede8;
  --text-000: #1a1814;
  --text-100: #2d2a24;
  --text-200: #4a4640;
  --text-300: #6b665e;
  --text-400: #9c978e;
  --accent-brand: #e8784f;
  --accent-main: #c4623a;
  --accent-soft: #d4714f;
  --accent-glow: rgba(232, 120, 79, 0.08);
  --green: #16a34a;
  --green-dim: rgba(22, 163, 74, 0.07);
  --blue: #2563eb;
  --blue-dim: rgba(37, 99, 235, 0.07);
  --yellow: #ca8a04;
  --yellow-dim: rgba(202, 138, 4, 0.07);
  --purple: #7c3aed;
  --purple-dim: rgba(124, 58, 237, 0.07);
  --border: rgba(26, 24, 20, 0.10);
  --border-subtle: rgba(26, 24, 20, 0.05);
  --shadow-sm: 0 1px 2px rgba(26, 24, 20, 0.05);
  --shadow-md: 0 2px 8px rgba(26, 24, 20, 0.07), 0 1px 2px rgba(26, 24, 20, 0.04);
  --radius: 8px;
  --radius-sm: 5px;
  --font-sans: 'Anthropic Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
  --font-serif: 'Source Serif 4', 'Noto Serif SC', Georgia, 'Times New Roman', Times, serif;
  --font-mono: ui-monospace, 'SF Mono', 'Fira Code', Menlo, Consolas, monospace;
}

html { font-size: 16px; scroll-behavior: smooth; }

body {
  font-family: var(--font-sans);
  background: var(--bg-100);
  color: var(--text-200);
  line-height: 1.65;
  min-height: 100vh;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* ── Subtle dot-grid texture (very faint on light) ── */
body::before {
  content: '';
  position: fixed;
  inset: 0;
  background-image: radial-gradient(circle, var(--text-000) 0.5px, transparent 0.5px);
  background-size: 20px 20px;
  opacity: 0.018;
  pointer-events: none;
  z-index: 0;
}

body > * { position: relative; z-index: 1; }

/* ── Header ── */
.site-header {
  background: var(--bg-000);
  border-bottom: 1px solid var(--border);
  padding: 0 0 1.5rem;
  position: relative;
}

.header-accent-bar {
  height: 3px;
  background: linear-gradient(90deg, var(--accent-brand), var(--accent-soft), var(--accent-brand));
  border-radius: 0 0 2px 2px;
}

.header-inner {
  max-width: 48rem;
  margin: 0 auto;
  padding: 1.5rem 1.5rem 0;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}

.brand {
  font-family: var(--font-sans);
  font-size: 1.125rem;
  font-weight: 600;
  letter-spacing: -0.02em;
  color: var(--text-000);
}

.brand-accent {
  color: var(--accent-brand);
  margin-left: 0.2em;
}

.header-date {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--text-400);
  letter-spacing: 0.04em;
}

/* ── Stats Bar ── */
.stats-bar {
  max-width: 48rem;
  margin: 1.75rem auto 0;
  padding: 0 1.5rem;
  display: flex;
  gap: 2.5rem;
}

.stat {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.stat-value {
  font-family: var(--font-sans);
  font-size: 1.375rem;
  font-weight: 700;
  color: var(--accent-brand);
  line-height: 1.2;
}

.stat-label {
  font-size: 0.6875rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--text-400);
  margin-top: 0.2rem;
}

/* ── Category Bar ── */
.category-bar {
  max-width: 48rem;
  margin: 1rem auto 0;
  padding: 0 1.5rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.category-pill {
  font-size: 0.75rem;
  padding: 0.2rem 0.6rem;
  border-radius: 999px;
  background: var(--accent-glow);
  color: var(--accent-main);
  border: 1px solid rgba(232, 120, 79, 0.15);
}

.category-pill em {
  font-style: normal;
  font-weight: 600;
  margin-left: 0.25em;
  color: var(--accent-brand);
}

/* ── Sections ── */
.section {
  max-width: 48rem;
  margin: 2.5rem auto 0;
  padding: 0 1.5rem;
}

.section-title {
  font-family: var(--font-serif);
  font-size: 1.25rem;
  font-weight: 500;
  letter-spacing: -0.015em;
  color: var(--text-000);
  padding-bottom: 0.6rem;
  border-bottom: 1px solid var(--border);
  margin-bottom: 1.25rem;
}

/* ── Table ── */
.table-wrap {
  overflow-x: auto;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  background: var(--bg-000);
  box-shadow: var(--shadow-sm);
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}

th {
  background: var(--bg-200);
  color: var(--text-400);
  font-weight: 500;
  font-size: 0.6875rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  padding: 0.65rem 0.875rem;
  text-align: left;
  border-bottom: 1px solid var(--border);
}

td {
  padding: 0.6rem 0.875rem;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-200);
}

tbody tr:hover { background: var(--bg-hover); }
tbody tr:last-child td { border-bottom: none; }

.row-num {
  font-family: var(--font-mono);
  color: var(--text-400);
  font-size: 0.75rem;
  width: 2.25rem;
}

.row-title { font-weight: 500; color: var(--text-100); }

.score-hot {
  color: var(--accent-brand);
  font-weight: 600;
}

.td-cat {
  font-size: 0.6875rem;
  padding: 0.1rem 0.45rem;
  border-radius: 999px;
  background: var(--blue-dim);
  color: var(--blue);
}

/* ── Story Cards ── */
.story-card {
  position: relative;
  background: var(--bg-000);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 1rem;
  overflow: hidden;
  transition: border-color 0.2s, box-shadow 0.2s;
  box-shadow: var(--shadow-sm);
}

/* Left accent bar */
.story-card::before {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  width: 3px;
  background: var(--accent-brand);
  border-radius: var(--radius) 0 0 var(--radius);
}

.story-card:hover {
  border-color: rgba(232, 120, 79, 0.3);
  box-shadow: var(--shadow-md);
}

.story-header {
  display: flex;
  align-items: flex-start;
  gap: 0.875rem;
  padding: 1rem 1.25rem 0.875rem 1.125rem;
  border-bottom: 1px solid var(--border-subtle);
}

.story-index {
  font-family: var(--font-mono);
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--accent-brand);
  line-height: 1;
  min-width: 2.25rem;
  opacity: 0.4;
}

.story-title-group { flex: 1; }

.story-title {
  font-family: var(--font-serif);
  font-size: 1.0625rem;
  font-weight: 500;
  letter-spacing: -0.01em;
  color: var(--text-000);
  line-height: 1.35;
  margin: 0;
}

.story-meta {
  display: flex;
  gap: 0.625rem;
  margin-top: 0.3rem;
}

.meta-cat {
  font-size: 0.6875rem;
  padding: 0.1rem 0.4rem;
  border-radius: 999px;
  background: var(--blue-dim);
  color: var(--blue);
  font-weight: 500;
}

.meta-score {
  font-family: var(--font-mono);
  font-size: 0.6875rem;
  color: var(--text-300);
}

.meta-comments {
  font-family: var(--font-mono);
  font-size: 0.6875rem;
  color: var(--text-400);
}

/* ── Story Body ── */
.story-body {
  padding: 1rem 1.25rem 1.25rem 1.125rem;
}

.story-link {
  margin-bottom: 0.75rem;
}

.story-link a {
  font-family: var(--font-mono);
  font-size: 0.6875rem;
  color: var(--text-400);
  text-decoration: none;
  word-break: break-all;
  transition: color 0.15s;
}

.story-link a:hover { color: var(--accent-brand); }

.field {
  margin-bottom: 0.75rem;
  font-size: 0.9375rem;
  line-height: 1.65;
}

.field:last-child { margin-bottom: 0; }

.field-label {
  display: inline-block;
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-400);
  margin-right: 0.5rem;
  min-width: 5em;
}

.field-important .field-label { color: var(--green); }

.field-important {
  padding: 0.5rem 0.75rem;
  background: var(--green-dim);
  border-radius: var(--radius-sm);
  border-left: 3px solid var(--green);
}

.key-points {
  list-style: none;
  padding-left: 0.375rem;
  margin-top: 0.25rem;
}

.key-points li {
  position: relative;
  padding-left: 1rem;
  margin-bottom: 0.3rem;
  color: var(--text-200);
}

.key-points li::before {
  content: '+';
  position: absolute;
  left: 0;
  top: 0;
  font-family: var(--font-mono);
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--accent-brand);
}

.summary-text {
  color: var(--text-300);
  font-size: 0.875rem;
  line-height: 1.7;
  margin-top: 0.15rem;
}

/* ── Keywords ── */
.keywords {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  margin-top: 0.5rem;
}

.keyword {
  font-size: 0.6875rem;
  font-family: var(--font-mono);
  padding: 0.1rem 0.45rem;
  border-radius: 999px;
  background: var(--purple-dim);
  color: var(--purple);
  border: 1px solid rgba(124, 58, 237, 0.12);
}

/* ── Comments ── */
.comments-section {
  margin-top: 0.875rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--border-subtle);
}

.comments-header {
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-400);
  margin-bottom: 0.5rem;
}

.comment {
  padding: 0.5rem 0.75rem;
  margin-bottom: 0.4rem;
  background: var(--bg-200);
  border-radius: var(--radius-sm);
  border-left: 2px solid var(--border);
}

.comment:last-child { margin-bottom: 0; }

.comment-author {
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--accent-main);
  margin-bottom: 0.15rem;
}

.comment-votes {
  font-family: var(--font-mono);
  font-size: 0.625rem;
  font-weight: 400;
  color: var(--text-400);
  margin-left: 0.4rem;
}

.comment-body {
  font-size: 0.875rem;
  color: var(--text-300);
  line-height: 1.55;
}

/* ── Segments ── */
.script-meta {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--text-400);
  margin-bottom: 0.875rem;
}

.segment {
  background: var(--bg-000);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 0.75rem 1rem;
  margin-bottom: 0.5rem;
  box-shadow: var(--shadow-sm);
}

.segment-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.4rem;
}

.seg-type {
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
}

.seg-type-opening .seg-type { background: var(--green-dim); color: var(--green); }
.seg-type-story_scan .seg-type { background: var(--blue-dim); color: var(--blue); }
.seg-type-closing .seg-type { background: var(--yellow-dim); color: var(--yellow); }

.seg-duration {
  font-family: var(--font-mono);
  font-size: 0.6875rem;
  color: var(--text-400);
}

.segment-text {
  font-size: 0.9375rem;
  color: var(--text-300);
  line-height: 1.7;
}

/* ── Footer ── */
.site-footer {
  margin-top: 3rem;
  padding: 1.25rem 0;
  border-top: 1px solid var(--border);
}

.footer-inner {
  max-width: 48rem;
  margin: 0 auto;
  padding: 0 1.5rem;
  font-size: 0.75rem;
  color: var(--text-400);
  text-align: center;
  letter-spacing: 0.02em;
}

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: var(--bg-200); }
::-webkit-scrollbar-thumb { background: rgba(26, 24, 20, 0.12); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: rgba(26, 24, 20, 0.2); }

/* ── Responsive ── */
@media (max-width: 640px) {
  .header-inner, .stats-bar, .category-bar, .section, .footer-inner { padding-left: 1rem; padding-right: 1rem; }
  .stats-bar { gap: 1.25rem; }
  .stat-value { font-size: 1.125rem; }
  .story-header { flex-direction: column; gap: 0.375rem; }
  .story-index { font-size: 1.25rem; }
  .story-meta { flex-wrap: wrap; }
}
"""
