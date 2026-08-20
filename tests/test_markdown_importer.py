"""Unit tests for markdown_importer."""

from src.pipeline.script.markdown_importer import (
    _clean_text,
    _split_into_sentences,
    parse_markdown_script,
)


SAMPLE_MARKDOWN = """# HN Daily 视频脚本：2026-08-18

## 封面

主标题：

**AI 内容，开始没人愿意读了**

副标题：

**假智库定向投喂 AI · 内存价格暴涨 500%**

日期：

**HN DAILY · 2026.08.18**

## 开场

昨天的 Hacker News 上，最值得关注的不是又发布了什么新模型，而是同时浮现的三个信号。

第一，AI 批量生产的内容，大家越来越懒得读了。

## 头条：AI;DR

[AI;DR，全称是 AI Didn't Read（AI 写的，不读）](https://www.rickmanelius.com/p/aidr-ai-didnt-read)。

模仿自互联网经典的 TL;DR（太长不读），读者会直接划走，拒绝阅读。

社区讨论：HN 评论区表示反对未经编辑的垃圾内容。

## 快讯

### Amazon 把搜索广告变成了“税”

[名博 Seth Godin 发文](https://seths.blog/2026/08/the-amazon-tax/)，将亚马逊的站内搜索广告比作一种“平台税”。

## 结尾

纵观今天所有的热点，我们可以清晰地看到 AI 浪潮正在加速。
"""


def test_clean_text():
    assert (
        _clean_text("**加粗** 与 [链接文本](https://example.com)") == "加粗 与 链接文本"
    )


def test_split_into_sentences():
    text = "第一句话。第二句话！第三句话？"
    sentences = _split_into_sentences(text)
    assert len(sentences) == 3
    assert sentences[0] == "第一句话。"


def test_parse_markdown_script():
    script = parse_markdown_script(SAMPLE_MARKDOWN, date="2026-08-18")
    assert script.title == "HN每日观察 | 2026-08-18"
    assert len(script.segments) == 4

    # 1. Check opening segment
    opening = script.segments[0]
    assert opening.segment_type == "opening"
    cover_card = opening.scene_elements[0]
    assert cover_card.props["headline"] == "AI 内容，开始没人愿意读了"
    assert cover_card.props["subtitle"] == "假智库定向投喂 AI · 内存价格暴涨 500%"

    # 2. Check story scan segment
    story_seg = script.segments[1]
    assert story_seg.segment_type == "story_scan"
    assert (
        len(story_seg.scene_elements) == 2
    )  # 1 headline evidence card + 1 comment card
    assert story_seg.scene_elements[0].props["title"] == "AI;DR"
    assert story_seg.scene_elements[0].props["template_id"] == "headline_v1"
    assert story_seg.scene_elements[1].props["template_id"] == "comment_single_v1"

    # 3. Check quick news segment
    quick_seg = script.segments[2]
    assert quick_seg.segment_type == "quick_news"
    assert len(quick_seg.scene_elements) == 1
    assert quick_seg.scene_elements[0].props["title"] == "Amazon 把搜索广告变成了“税”"

    # 4. Check closing segment
    closing_seg = script.segments[3]
    assert closing_seg.segment_type == "closing"
    assert len(closing_seg.scene_elements) == 1
    assert closing_seg.scene_elements[0].props["template_id"] == "closing_v1"
    assert len(closing_seg.scene_elements[0].props["summary_items"]) == 1
