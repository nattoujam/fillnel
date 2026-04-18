import json
from unittest.mock import MagicMock, patch

import pytest

from fillnel.steps import cleanup, collect, register

from fillnel.services.raindrop import UNSORTED_COLLECTION_ID

COLLECTION_ID = UNSORTED_COLLECTION_ID


# --- cleanup ---

class TestCleanup:
    def test_deletes_items_in_collection(self):
        client = MagicMock()
        client.get_bookmarks.return_value = [{"_id": 1}, {"_id": 2}]

        cleanup.run(client, COLLECTION_ID)

        client.get_bookmarks.assert_called_once_with(collection_id=COLLECTION_ID)
        client.delete_bookmarks.assert_called_once_with([1, 2])

    def test_skips_delete_when_no_items(self):
        client = MagicMock()
        client.get_bookmarks.return_value = []

        cleanup.run(client, COLLECTION_ID)

        client.delete_bookmarks.assert_not_called()


# --- collect ---

ARTICLES = [
    {"url": "https://a.com", "summary": "AI記事の要約"},
    {"url": "https://b.com", "summary": "TS記事の要約"},
    {"url": "https://c.com", "summary": "その他の要約"},
]


class TestCollect:
    def test_returns_articles_from_gemini(self, tmp_path, monkeypatch):
        import fillnel.services.profile as profile_svc
        monkeypatch.setattr(profile_svc, "PROFILE_PATH", tmp_path / "profile.json")

        gemini = MagicMock()
        gemini.collect_articles.return_value = ARTICLES

        result = collect.run(gemini)

        assert len(result) == 3
        gemini.collect_articles.assert_called_once()

    def test_caps_at_max_articles(self, tmp_path, monkeypatch):
        import fillnel.services.profile as profile_svc
        monkeypatch.setattr(profile_svc, "PROFILE_PATH", tmp_path / "profile.json")

        gemini = MagicMock()
        gemini.collect_articles.return_value = ARTICLES * 4  # 12件

        result = collect.run(gemini)

        assert len(result) <= 10


# --- register ---

class TestRegister:
    def test_registers_to_collection(self):
        client = MagicMock()
        articles = [{"url": "https://a.com", "summary": "要約"}]

        register.run(client, articles, COLLECTION_ID)

        client.create_bookmark.assert_called_once()
        bookmark = client.create_bookmark.call_args[0][0]
        assert bookmark["collection"] == {"$id": COLLECTION_ID}
        assert "tags" not in bookmark
        assert "title" not in bookmark

    def test_registers_all_articles(self):
        client = MagicMock()
        articles = [{"url": f"https://example.com/{i}", "summary": ""} for i in range(5)]

        register.run(client, articles, COLLECTION_ID)

        assert client.create_bookmark.call_count == 5

    def test_empty_articles(self):
        client = MagicMock()
        register.run(client, [], COLLECTION_ID)
        client.create_bookmark.assert_not_called()
