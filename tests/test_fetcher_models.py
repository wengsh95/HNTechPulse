from src.providers.fetcher.models import HNStory, HNComment


class TestFetcherModels:
    def test_hn_story_creation(self):
        story = HNStory(
            id=123,
            title="Test Story",
            url="https://example.com",
            score=100,
            descendants=50,
            time=1700000000,
            text=None,
            by="user",
        )
        assert story.id == 123
        assert story.title == "Test Story"
        assert story.by == "user"
        assert story.text is None

    def test_hn_story_defaults(self):
        story = HNStory(
            id=1,
            title="T",
            url=None,
            score=0,
            descendants=0,
            time=0,
            text=None,
        )
        assert story.by is None

    def test_hn_comment_creation(self):
        comment = HNComment(
            id=456,
            author="commenter",
            text="Great post",
            time=1700000100,
        )
        assert comment.id == 456
        assert comment.author == "commenter"
        assert comment.text == "Great post"

    def test_hn_story_importable_from_fetcher(self):
        from src.providers.fetcher.models import HNStory, HNComment

        assert HNStory is not None
        assert HNComment is not None
