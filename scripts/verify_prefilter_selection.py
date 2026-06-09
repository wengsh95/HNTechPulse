"""End-to-end verification of the prefilter news-focus change.

Creates a realistic pool of HN stories (mix of news, Show HN, Ask HN, tutorials)
and runs the actual Prefilter with a smart keyword-based LLM mock. Prints the
top-N selected stories so we can eyeball that news-type dominates.
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

# Make project importable when run from any cwd
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.core.models import ContentComment, ContentItem, ContentPackage  # noqa: E402
from src.pipeline.prefilter import Prefilter  # noqa: E402


# Realistic pool: (id, title, url, hn_score, comment_count, comments, expected_type)
STORIES = [
    # --- 7 clear news events ---
    ("1", "Anthropic raises $10B at $200B valuation", "https://anthropic.com/news/10b", 1200, 540, ["game changer for the industry"], "news"),
    ("2", "Critical RCE in OpenSSH disclosed — patch now", "https://openssh.com/advisory", 980, 320, ["prod boxes need patching tonight"], "news"),
    ("3", "OpenAI announces GPT-6 with 10x context window", "https://openai.com/blog/gpt6", 1800, 800, ["huge leap, but also huge infra bill"], "news"),
    ("4", "Nvidia unveils Blackwell Ultra GPU at GTC", "https://nvidia.com/blackwell-ultra", 720, 210, ["perf/watt is the real story"], "news"),
    ("5", "Major data breach at X exposes 200M user records", "https://x.com/breach", 1500, 1100, ["the second one this quarter"], "news"),
    ("6", "EU passes landmark AI Act amendment on open source", "https://europa.eu/ai-act-amendment", 600, 180, ["big deal for OSS devs"], "news"),
    ("7", "Linux kernel 7.0 released with Rust-first drivers", "https://kernel.org/7.0", 540, 160, ["finally"], "news"),
    # --- 4 Show HN (product launches, lower news value) ---
    ("8", "Show HN: I built a faster Postgres in 6 months", "https://github.com/x/fastpg", 420, 95, ["neat project"], "show"),
    ("9", "Show HN: A terminal UI for Kubernetes", "https://github.com/x/kui", 280, 60, ["looks polished"], "show"),
    ("10", "Show HN: Local-first note app with CRDT sync", "https://github.com/x/notes", 180, 40, ["i use obsidian but cool"], "show"),
    ("11", "Show HN: GPU-accelerated regex engine", "https://github.com/x/gpuregex", 150, 25, ["benchmark numbers?"], "show"),
    # --- 4 Ask HN (questions, not news) ---
    ("12", "Ask HN: How do you handle on-call at small startups?", "https://news.ycombinator.com/item?id=12", 350, 220, ["pagerduty free tier"], "ask"),
    ("13", "Ask HN: What's your favorite debugging tool in 2026?", "https://news.ycombinator.com/item?id=13", 220, 150, ["just gdb"], "ask"),
    ("14", "Ask HN: Should I learn Rust or Go in 2026?", "https://news.ycombinator.com/item?id=14", 480, 380, ["hot debate as always"], "ask"),
    ("15", "Ask HN: Why is my Lambda cold start 8s?", "https://news.ycombinator.com/item?id=15", 90, 45, ["cold start tax"], "ask"),
    # --- 5 tutorials / resources / opinion (not news) ---
    ("16", "Tutorial: Building a vector DB from scratch", "https://blog.x/vector-db", 380, 90, ["nice writeup"], "tutorial"),
    ("17", "Why I switched from VSCode to Zed (after 5 years)", "https://blog.x/zed", 200, 110, ["zed is fast but..."], "opinion"),
    ("18", "A curated list of 200 CLI tools", "https://github.com/x/awesome-cli", 90, 30, ["bookmarked"], "resource"),
    ("19", "Deep dive: How Linux page tables work", "https://blog.x/page-tables", 150, 50, ["loved it"], "tutorial"),
    ("20", "On the state of developer experience in 2026", "https://blog.x/dx-2026", 110, 40, ["decent take"], "opinion"),
]


def llm_decision(idx, item):
    """Smart mock: judges news_focus/newsworthiness from title + comment text."""
    title = (item.title or "").lower()
    comments = " ".join(c.content for c in item.comments).lower()

    # News-type signals
    news_event_signals = [
        "raises $", "raises $", "valuation", "disclosed", "patch now", "rce",
        "announces", "unveils", "breach", "exposes", "passes", "landmark",
        "amendment", "released", "kernel 7.0", "gpt-6", "blackwell",
    ]
    is_news_event = any(s in title for s in news_event_signals)

    # Show HN / Ask HN / tutorial signals
    is_show_hn = title.startswith("show hn")
    is_ask_hn = title.startswith("ask hn")
    is_tutorial = "tutorial" in title or "how " in title and "works" in title
    is_resource = "curated" in title or "awesome" in title or "list of" in title
    is_opinion = "why i switched" in title or "on the state of" in title

    if is_news_event:
        news_focus = 5
        newsworthiness = 5
        category = "ai_company" if "anthropic" in title or "openai" in title else \
                   "security" if "rce" in title or "breach" in title else \
                   "hardware" if "nvidia" in title or "gpu" in title else \
                   "policy" if "eu" in title or "act" in title else \
                   "infra"
    elif is_ask_hn:
        news_focus = 1
        newsworthiness = 2
        category = "other"
    elif is_show_hn:
        news_focus = 2
        newsworthiness = 3
        category = "developer_tools"
    elif is_tutorial:
        news_focus = 1
        newsworthiness = 2
        category = "developer_tools"
    elif is_resource:
        news_focus = 1
        newsworthiness = 1
        category = "other"
    elif is_opinion:
        news_focus = 1
        newsworthiness = 2
        category = "culture"
    else:
        news_focus = 3
        newsworthiness = 3
        category = "other"

    # Boost comment-heat for Ask HN (high discussion but not news)
    if is_ask_hn and (item.comment_count or 0) > 200:
        newsworthiness = max(newsworthiness, 3)  # bypass min threshold

    return {
        "index": idx,
        "keep": True,
        "reason": f"simulated decision for {item.source_id}",
        "category": category,
        "news_focus": news_focus,
        "newsworthiness": newsworthiness,
    }


def make_package():
    items = []
    for sid, title, url, score, cc, comment_texts, _ in STORIES:
        comments = [
            ContentComment(
                author=f"u{i}",
                content=ct,
                source_id=f"c{i}",
                depth=1,
            )
            for i, ct in enumerate(comment_texts)
        ]
        items.append(
            ContentItem(
                source="hackernews",
                source_id=sid,
                title=title,
                url=url,
                score=score,
                comment_count=cc,
                comments=comments,
                comments_partial=True,
            )
        )
    return ContentPackage(date="2026-06-08", items=items)


def main():
    # Use a sandbox dir under data/ so cache writes don't pollute real data
    import os
    sandbox = ROOT / "data" / "_verify_prefilter"
    sandbox.mkdir(parents=True, exist_ok=True)
    os.chdir(sandbox)

    content = make_package()

    llm = MagicMock()
    llm.prefilter_stories.side_effect = lambda stories: [
        llm_decision(idx, content.items[idx]) for (idx, *_rest) in stories
    ]

    config = {
        "logging": {"level": "WARNING"},
        "pipeline": {"target_story_count": 3},  # base.yaml defaults to daily 3 stories
        "prefilter": {
            "enabled": True,
            "min_keep": 5,
            "min_newsworthiness": 3,
            "temperature": 0.1,
            "comment_preview_enabled": True,
            "comment_preview_count": 5,
            "news_focus_weight": 2.0,
            "newsworthiness_weight": 1.5,
        },
        "llm": {"provider": "mock", "model": "mock"},
    }

    prefilter = Prefilter(llm, config, debug=False)
    result = prefilter.filter(content, "2026-06-08")

    # Type lookup for labelling
    type_by_id = {sid: t for sid, *_rest, t in STORIES}

    print(f"\n=== Selected top {len(result.items)} of {len(STORIES)} stories ===\n")
    print(f"{'#':<3} {'ID':<4} {'Type':<10} {'NF':<3} {'NW':<3} {'EScore':<8} {'HN':<5} {'Title'}")
    print("-" * 110)
    for i, item in enumerate(result.items, 1):
        nf = item.news_focus if item.news_focus is not None else 0
        nw = item.newsworthiness if item.newsworthiness is not None else 0
        es = item.editorial_score if item.editorial_score is not None else 0
        print(
            f"{i:<3} {item.source_id:<4} {type_by_id.get(item.source_id, '?'):<10} "
            f"{nf:<3} {nw:<3} {es:<8.1f} {item.score or 0:<5} {item.title}"
        )

    # Verify
    selected_types = [type_by_id.get(it.source_id, "?") for it in result.items]
    news_count = sum(1 for t in selected_types if t == "news")
    show_count = sum(1 for t in selected_types if t == "show")
    ask_count = sum(1 for t in selected_types if t == "ask")
    other_count = sum(1 for t in selected_types if t in ("tutorial", "resource", "opinion"))

    print(f"\n=== Selection breakdown ===")
    print(f"news:    {news_count}/{len(result.items)}")
    print(f"show:    {show_count}/{len(result.items)}")
    print(f"ask:     {ask_count}/{len(result.items)}")
    print(f"tutorial/resource/opinion: {other_count}/{len(result.items)}")

    # Assertions
    assert news_count >= 3, f"FAIL: expected at least 3 news stories, got {news_count}"
    assert other_count <= 1, f"FAIL: expected at most 1 non-news non-ask, got {other_count}"
    print(f"\n[PASS] Selection prefers news-type: {news_count}/{len(result.items)} are news events")


if __name__ == "__main__":
    main()
