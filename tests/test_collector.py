from unittest.mock import patch

import pytest

from fillnel.services import collector as collector_svc


class TestLoadFeeds:
    def test_returns_empty_when_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(collector_svc, "FEEDS_PATH", tmp_path / "feeds.yml")
        assert collector_svc.load_feeds() == []

    def test_returns_urls_from_yaml(self, tmp_path, monkeypatch):
        feeds_path = tmp_path / "feeds.yml"
        feeds_path.write_text("feeds:\n  - https://zenn.dev/feed\n  - https://qiita.com/popular-items/feed\n")
        monkeypatch.setattr(collector_svc, "FEEDS_PATH", feeds_path)
        assert collector_svc.load_feeds() == [
            "https://zenn.dev/feed",
            "https://qiita.com/popular-items/feed",
        ]

    def test_returns_empty_when_feeds_key_missing(self, tmp_path, monkeypatch):
        feeds_path = tmp_path / "feeds.yml"
        feeds_path.write_text("{}\n")
        monkeypatch.setattr(collector_svc, "FEEDS_PATH", feeds_path)
        assert collector_svc.load_feeds() == []


class TestStripHtml:
    def test_removes_tags(self):
        assert collector_svc._strip_html("<p>hello <b>world</b></p>") == "hello world"

    def test_passes_plain_text(self):
        assert collector_svc._strip_html("plain text") == "plain text"

    def test_returns_empty_for_tags_only(self):
        assert collector_svc._strip_html("<br/><hr/>") == ""


class TestFetchFeed:
    def _make_entry(self, title="記事", link="https://a.com", summary="要約"):
        from unittest.mock import MagicMock
        e = MagicMock()
        e.get.side_effect = lambda key, default="": {"title": title, "link": link, "summary": summary}.get(key, default)
        return e

    def _make_parsed(self, entries):
        from unittest.mock import MagicMock
        p = MagicMock()
        p.entries = entries
        return p

    def test_returns_articles(self):
        entry = self._make_entry()
        with patch("fillnel.services.collector.feedparser.parse", return_value=self._make_parsed([entry])):
            result = collector_svc.fetch_feed("https://example.com/feed")
        assert result == [{"title": "記事", "url": "https://a.com", "excerpt": "要約"}]

    def test_skips_entries_without_link(self):
        entry = self._make_entry(link="")
        with patch("fillnel.services.collector.feedparser.parse", return_value=self._make_parsed([entry])):
            result = collector_svc.fetch_feed("https://example.com/feed")
        assert result == []

    def test_strips_html_from_summary(self):
        entry = self._make_entry(summary="<p>要約</p>")
        with patch("fillnel.services.collector.feedparser.parse", return_value=self._make_parsed([entry])):
            result = collector_svc.fetch_feed("https://example.com/feed")
        assert result[0]["excerpt"] == "要約"

    def test_returns_empty_on_exception(self):
        with patch("fillnel.services.collector.feedparser.parse", side_effect=Exception("error")):
            result = collector_svc.fetch_feed("https://example.com/feed")
        assert result == []


class TestCollectFromFeeds:
    def test_deduplicates_urls(self, tmp_path, monkeypatch):
        feeds_path = tmp_path / "feeds.yml"
        feeds_path.write_text("feeds:\n  - https://feed1.com\n  - https://feed2.com\n")
        monkeypatch.setattr(collector_svc, "FEEDS_PATH", feeds_path)

        article = {"title": "重複記事", "url": "https://same.com", "excerpt": ""}
        with patch("fillnel.services.collector.fetch_feed", return_value=[article]):
            result = collector_svc.collect_from_feeds()

        assert len(result) == 1
        assert result[0]["url"] == "https://same.com"

    def test_returns_empty_when_no_feeds(self, tmp_path, monkeypatch):
        monkeypatch.setattr(collector_svc, "FEEDS_PATH", tmp_path / "feeds.yml")
        result = collector_svc.collect_from_feeds()
        assert result == []
