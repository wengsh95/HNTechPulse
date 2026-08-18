from src.providers.enricher.relevance import assess_article_relevance


def test_root_aggregator_without_title_signal_is_rejected():
    result = assess_article_relevance(
        "Hacker News front page as a site",
        "The post proposes a variant of the Raft consensus algorithm.",
        url="https://example.com/",
    )

    assert result.accepted is False
    assert result.reason == "root_page_has_no_title_signal"


def test_article_with_title_signal_is_accepted():
    result = assess_article_relevance(
        "DynIP dynamic DNS updates",
        "DynIP provides dynamic DNS updates and DNSSEC support for home networks.",
        url="https://example.com/dynip",
    )

    assert result.accepted is True
    assert result.score > 0


def test_title_without_usable_tokens_does_not_block_extraction():
    result = assess_article_relevance(
        "—",
        "这是一篇介绍系统设计的文章。",
        url="https://example.com/article",
    )

    assert result.accepted is True


def test_low_information_extraction_is_not_mislabeled_as_wrong_article():
    result = assess_article_relevance(
        "Story",
        "A" * 300,
        url="https://example.com/story",
    )

    assert result.accepted is True
    assert result.reason == "body_has_insufficient_lexical_signal"
