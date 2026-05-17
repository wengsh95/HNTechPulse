import json
from pathlib import Path

from src.core.models import ContentItem, ContentPackage
from src.pipeline.content_hydrator import merge_enrichment_into_content


def test_merge_enrichment_overlay_updates_render_fields(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-05-17"
    data_dir = Path("data") / date
    data_dir.mkdir(parents=True)

    content = ContentPackage(
        date=date,
        items=[
            ContentItem(
                source="hackernews",
                source_id="42",
                title="Original title",
                url="https://example.com",
                article_images=["images/base.jpg"],
                image_candidates=[{"path": "images/base.jpg", "source": "page"}],
                keywords=["旧关键词"],
                why_it_matters="旧价值",
            )
        ],
    )
    (data_dir / "enrichment.json").write_text(
        json.dumps(
            {
                "date": date,
                "items": {
                    "42": {
                        "article_images": ["images/editor.jpg", "images/base.jpg"],
                        "image_candidates": [
                            {"path": "images/editor.jpg", "source": "upload"}
                        ],
                        "keywords": ["MCP协议", "企业部署"],
                        "why_it_matters": "改变开发工作流",
                        "next_watch": "关注企业部署",
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    merge_enrichment_into_content(content, date)

    item = content.items[0]
    assert item.article_images == ["images/editor.jpg", "images/base.jpg"]
    assert item.image_candidates == [{"path": "images/editor.jpg", "source": "upload"}]
    assert item.keywords == ["MCP协议", "企业部署"]
    assert item.why_it_matters == "改变开发工作流"
    assert item.next_watch == "关注企业部署"


def test_merge_enrichment_overlay_preserves_base_when_values_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-05-17"
    data_dir = Path("data") / date
    data_dir.mkdir(parents=True)

    content = ContentPackage(
        date=date,
        items=[
            ContentItem(
                source="hackernews",
                source_id="42",
                title="Original title",
                url="https://example.com",
                keywords=["保留关键词"],
                why_it_matters="保留价值",
            )
        ],
    )
    (data_dir / "enrichment.json").write_text(
        json.dumps(
            {
                "date": date,
                "items": {
                    "42": {
                        "keywords": [],
                        "why_it_matters": "",
                        "next_watch": None,
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    merge_enrichment_into_content(content, date)

    assert content.items[0].keywords == ["保留关键词"]
    assert content.items[0].why_it_matters == "保留价值"
    assert content.items[0].next_watch is None
