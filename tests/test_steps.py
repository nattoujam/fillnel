import json
from unittest.mock import MagicMock, patch

import pytest

from fillnel.steps import check_links, cleanup, collect, enrich, rebuild_profile, register
from fillnel.steps.check_links import _check_url

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


# --- learn ---

class TestEnrich:
    @pytest.fixture(autouse=True)
    def no_sleep(self, monkeypatch):
        monkeypatch.setattr("fillnel.steps.enrich.time.sleep", lambda _: None)

    def test_skips_when_no_items(self):
        client = MagicMock()
        client.get_bookmarks.return_value = []
        gemini = MagicMock()

        enrich.run(client, gemini, favorite_collection_id=99)

        gemini.estimate_tags.assert_not_called()

    def test_estimates_tags_for_untagged_items(self):
        client = MagicMock()
        client.get_bookmarks.return_value = [
            {"_id": 1, "title": "AI記事", "link": "https://a.com", "tags": [], "excerpt": "既存要約"},
        ]
        client.get_tags.return_value = ["AI", "TypeScript"]
        gemini = MagicMock()
        gemini.estimate_tags.return_value = ["AI", "TypeScript"]

        enrich.run(client, gemini, favorite_collection_id=99)

        gemini.estimate_tags.assert_called_once_with(
            title="AI記事",
            url="https://a.com",
            existing_tags=["AI", "TypeScript"],
        )
        client.update_bookmark.assert_called_once_with(1, {"tags": ["AI", "TypeScript"]})

    def test_skips_gemini_when_already_tagged_and_has_excerpt(self):
        client = MagicMock()
        client.get_bookmarks.return_value = [
            {"_id": 1, "title": "AI記事", "link": "https://a.com", "tags": ["AI"], "excerpt": "既存要約"},
        ]
        gemini = MagicMock()

        enrich.run(client, gemini, favorite_collection_id=99)

        gemini.estimate_tags.assert_not_called()
        gemini.summarize_article.assert_not_called()
        client.update_bookmark.assert_not_called()

    def test_generates_excerpt_for_items_without_one(self):
        client = MagicMock()
        client.get_bookmarks.return_value = [
            {"_id": 1, "title": "AI記事", "link": "https://a.com", "tags": ["AI"], "excerpt": ""},
        ]
        gemini = MagicMock()
        gemini.summarize_article.return_value = "生成された要約"

        enrich.run(client, gemini, favorite_collection_id=99)

        gemini.summarize_article.assert_called_once_with(title="AI記事", url="https://a.com")
        client.update_bookmark.assert_called_once_with(1, {"excerpt": "生成された要約"})

    def test_combines_excerpt_and_tags_in_single_update(self):
        client = MagicMock()
        client.get_bookmarks.return_value = [
            {"_id": 1, "title": "AI記事", "link": "https://a.com", "tags": [], "excerpt": ""},
        ]
        client.get_tags.return_value = []
        gemini = MagicMock()
        gemini.summarize_article.return_value = "生成された要約"
        gemini.estimate_tags.return_value = ["AI"]

        enrich.run(client, gemini, favorite_collection_id=99)

        client.update_bookmark.assert_called_once_with(1, {"excerpt": "生成された要約", "tags": ["AI"]})

    def test_force_retags_already_tagged_items(self):
        client = MagicMock()
        client.get_bookmarks.return_value = [
            {"_id": 1, "title": "AI記事", "link": "https://a.com", "tags": ["旧タグ"], "excerpt": "既存要約"},
        ]
        client.get_tags.return_value = ["AI", "Python"]
        gemini = MagicMock()
        gemini.estimate_tags.return_value = ["AI", "Python"]

        enrich.run(client, gemini, favorite_collection_id=99, force=True)

        gemini.estimate_tags.assert_called_once()
        client.update_bookmark.assert_called_once_with(1, {"tags": ["AI", "Python"]})

    def test_skips_update_when_estimation_returns_empty(self):
        client = MagicMock()
        client.get_bookmarks.return_value = [
            {"_id": 1, "title": "記事", "link": "https://a.com", "tags": [], "excerpt": "既存要約"},
        ]
        gemini = MagicMock()
        gemini.estimate_tags.return_value = []

        enrich.run(client, gemini, favorite_collection_id=99)

        client.update_bookmark.assert_not_called()


# --- rebuild_profile ---

class TestRebuildProfile:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path, monkeypatch):
        import fillnel.services.profile as profile_svc
        monkeypatch.setattr(profile_svc, "PROFILE_PATH", tmp_path / "profile.json")

    def _make_gemini(self, vec=None):
        gemini = MagicMock()
        gemini.embed_text.return_value = vec or [1.0, 0.0]
        return gemini

    def test_updates_profile_from_tagged_items(self):
        import fillnel.services.profile as profile_svc

        client = MagicMock()
        client.get_bookmarks.return_value = [
            {"_id": 1, "title": "AI記事", "link": "https://a.com", "tags": ["AI", "機械学習"], "excerpt": "要約"},
        ]

        rebuild_profile.run(client, self._make_gemini(), favorite_collection_id=99)

        profile = profile_svc.load()
        assert profile["tags"]["AI"] == 2.0
        assert profile["tags"]["機械学習"] == 2.0
        assert profile["domains"]["a.com"] == 1

    def test_resets_profile_before_recalculating(self):
        import fillnel.services.profile as profile_svc

        profile_svc.save({"tags": {"古いタグ": 99.0}, "domains": {}})

        client = MagicMock()
        client.get_bookmarks.return_value = [
            {"_id": 1, "title": "AI記事", "link": "https://a.com", "tags": ["AI"], "excerpt": "要約"},
        ]

        rebuild_profile.run(client, self._make_gemini(), favorite_collection_id=99)

        profile = profile_svc.load()
        assert "古いタグ" not in profile["tags"]
        assert profile["tags"]["AI"] == 2.0

    def test_returns_favorites_with_excerpt(self):
        client = MagicMock()
        client.get_bookmarks.return_value = [
            {"_id": 1, "title": "AI記事", "link": "https://a.com", "tags": ["AI"], "excerpt": "AI要約"},
            {"_id": 2, "title": "TS記事", "link": "https://b.com", "tags": ["TypeScript"], "excerpt": ""},
        ]

        result = rebuild_profile.run(client, self._make_gemini(), favorite_collection_id=99)

        assert result == [{"title": "AI記事", "excerpt": "AI要約"}]

    def test_empty_favorites(self):
        import fillnel.services.profile as profile_svc

        client = MagicMock()
        client.get_bookmarks.return_value = []

        result = rebuild_profile.run(client, self._make_gemini(), favorite_collection_id=99)

        assert result == []
        profile = profile_svc.load()
        assert profile["tags"] == {}
        assert profile["domains"] == {}

    def test_stores_profile_vector(self):
        import fillnel.services.profile as profile_svc

        client = MagicMock()
        client.get_bookmarks.return_value = [
            {"_id": 1, "title": "AI記事", "link": "https://a.com", "tags": [], "excerpt": "要約"},
        ]
        gemini = self._make_gemini([0.5, 0.5])

        rebuild_profile.run(client, gemini, favorite_collection_id=99)

        profile = profile_svc.load()
        assert "profile_vector" in profile
        assert len(profile["profile_vector"]) == 2

    def test_caches_new_article_embedding(self):
        import fillnel.services.profile as profile_svc

        client = MagicMock()
        client.get_bookmarks.return_value = [
            {"_id": 1, "title": "AI記事", "link": "https://a.com", "tags": [], "excerpt": "要約"},
        ]
        gemini = self._make_gemini()

        rebuild_profile.run(client, gemini, favorite_collection_id=99)

        profile = profile_svc.load()
        assert "https://a.com" in profile["embedding_cache"]
        gemini.embed_text.assert_called_once()

    def test_uses_cached_embedding_on_second_run(self):
        client = MagicMock()
        item = {"_id": 1, "title": "AI記事", "link": "https://a.com", "tags": [], "excerpt": "要約"}
        client.get_bookmarks.return_value = [item]
        gemini = self._make_gemini()

        rebuild_profile.run(client, gemini, favorite_collection_id=99)
        rebuild_profile.run(client, gemini, favorite_collection_id=99)

        # 2回実行しても embed_text は1回だけ
        assert gemini.embed_text.call_count == 1

    def test_purges_stale_cache_entries(self):
        import fillnel.services.profile as profile_svc

        client = MagicMock()
        client.get_bookmarks.return_value = [
            {"_id": 1, "title": "残る記事", "link": "https://a.com", "tags": [], "excerpt": "要約"},
        ]
        gemini = self._make_gemini()

        # 初回: a.com と b.com をキャッシュ
        import fillnel.services.profile as ps
        ps.save({"tags": {}, "domains": {}, "embedding_cache": {
            "https://b.com": {"hash": "oldhash", "vector": [0.1, 0.2]},
        }})

        rebuild_profile.run(client, gemini, favorite_collection_id=99)

        profile = profile_svc.load()
        assert "https://b.com" not in profile["embedding_cache"]
        assert "https://a.com" in profile["embedding_cache"]


# --- collect ---

RSS_ARTICLES = [
    {"title": "AI記事", "url": "https://a.com", "excerpt": "AI記事の要約"},
    {"title": "TS記事", "url": "https://b.com", "excerpt": "TS記事の要約"},
    {"title": "その他", "url": "https://c.com", "excerpt": "その他の要約"},
]


class TestCollect:
    @pytest.fixture(autouse=True)
    def patch_rss_and_embedding(self, monkeypatch):
        import fillnel.services.collector as collector_svc
        import fillnel.services.embedding as embedding_svc
        import fillnel.services.profile as profile_svc
        monkeypatch.setattr(collector_svc, "collect_from_feeds", lambda: RSS_ARTICLES)
        monkeypatch.setattr(embedding_svc, "score_articles", lambda articles, profile_vector, client: articles)
        monkeypatch.setattr(profile_svc, "load", lambda: {"tags": {}, "domains": {}, "profile_vector": [1.0, 0.0]})

    def test_returns_articles_from_filter(self):
        gemini = MagicMock()
        gemini.filter_articles.return_value = RSS_ARTICLES

        result = collect.run(gemini)

        assert len(result) == 3
        gemini.filter_articles.assert_called_once()

    def test_passes_favorites_to_filter(self):
        gemini = MagicMock()
        gemini.filter_articles.return_value = RSS_ARTICLES[:1]
        favorites = [{"title": "お気に入り", "excerpt": "要約"}]

        collect.run(gemini, favorites=favorites)

        _, called_favorites = gemini.filter_articles.call_args[0]
        assert called_favorites == favorites

    def test_caps_at_max_articles(self, monkeypatch):
        import fillnel.services.collector as collector_svc
        many = [{"title": f"記事{i}", "url": f"https://example.com/{i}", "excerpt": ""} for i in range(50)]
        monkeypatch.setattr(collector_svc, "collect_from_feeds", lambda: many)

        gemini = MagicMock()
        gemini.filter_articles.return_value = many[:15]

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
        assert "title" not in bookmark  # titleなし記事はフィールドを送らない

    def test_registers_with_title_when_present(self):
        client = MagicMock()
        articles = [{"url": "https://a.com", "title": "記事タイトル", "summary": "要約"}]

        register.run(client, articles, COLLECTION_ID)

        bookmark = client.create_bookmark.call_args[0][0]
        assert bookmark["title"] == "記事タイトル"

    def test_registers_all_articles(self):
        client = MagicMock()
        articles = [{"url": f"https://example.com/{i}", "summary": ""} for i in range(5)]

        register.run(client, articles, COLLECTION_ID)

        assert client.create_bookmark.call_count == 5

    def test_empty_articles(self):
        client = MagicMock()
        register.run(client, [], COLLECTION_ID)
        client.create_bookmark.assert_not_called()


# --- check_links ---

BROKEN_ID = 55
NORMAL_ITEM = {"_id": 1, "link": "https://a.com", "collection": {"$id": 10}}
UNSORTED_ITEM = {"_id": 2, "link": "https://b.com", "collection": {"$id": UNSORTED_COLLECTION_ID}}
BROKEN_ITEM = {"_id": 3, "link": "https://c.com", "collection": {"$id": BROKEN_ID}}


class TestCheckUrl:  # _check_url は check_links モジュール内のヘルパー
    def _mock_head(self, status_code):
        resp = MagicMock()
        resp.status_code = status_code
        return resp

    def test_returns_broken_on_404(self):
        with patch("fillnel.steps.check_links.requests.head", return_value=self._mock_head(404)):
            is_broken, reason = _check_url("https://example.com")
        assert is_broken is True
        assert "404" in reason

    def test_returns_broken_on_410(self):
        with patch("fillnel.steps.check_links.requests.head", return_value=self._mock_head(410)):
            is_broken, reason = _check_url("https://example.com")
        assert is_broken is True
        assert "410" in reason

    def test_returns_not_broken_on_200(self):
        with patch("fillnel.steps.check_links.requests.head", return_value=self._mock_head(200)):
            is_broken, _ = _check_url("https://example.com")
        assert is_broken is False

    def test_falls_back_to_get_on_405(self):
        with patch("fillnel.steps.check_links.requests.head", return_value=self._mock_head(405)):
            with patch("fillnel.steps.check_links.requests.get", return_value=self._mock_head(404)) as mock_get:
                is_broken, _ = _check_url("https://example.com")
        assert is_broken is True
        mock_get.assert_called_once()

    def test_returns_not_broken_on_request_exception(self):
        import requests as req
        with patch("fillnel.steps.check_links.requests.head", side_effect=req.RequestException("timeout")):
            is_broken, _ = _check_url("https://example.com")
        assert is_broken is False


class TestCheckLinks:
    @pytest.fixture(autouse=True)
    def no_sleep(self, monkeypatch):
        monkeypatch.setattr("fillnel.steps.check_links.time.sleep", lambda _: None)

    def test_skips_unsorted_collection(self):
        client = MagicMock()
        client.get_bookmarks.return_value = [UNSORTED_ITEM]
        with patch("fillnel.steps.check_links._check_url") as mock_check:
            check_links.run(client, BROKEN_ID)
        mock_check.assert_not_called()

    def test_skips_broken_link_collection(self):
        client = MagicMock()
        client.get_bookmarks.return_value = [BROKEN_ITEM]
        with patch("fillnel.steps.check_links._check_url") as mock_check:
            check_links.run(client, BROKEN_ID)
        mock_check.assert_not_called()

    def test_moves_broken_link_to_collection(self):
        client = MagicMock()
        client.get_bookmarks.return_value = [NORMAL_ITEM]
        with patch("fillnel.steps.check_links._check_url", return_value=(True, "HTTP 404")):
            check_links.run(client, BROKEN_ID)
        client.update_bookmark.assert_called_once_with(1, {"collection": {"$id": BROKEN_ID}})

    def test_does_not_move_live_links(self):
        client = MagicMock()
        client.get_bookmarks.return_value = [NORMAL_ITEM]
        with patch("fillnel.steps.check_links._check_url", return_value=(False, "")):
            check_links.run(client, BROKEN_ID)
        client.update_bookmark.assert_not_called()

    def test_skips_items_without_url(self):
        client = MagicMock()
        client.get_bookmarks.return_value = [{"_id": 9, "link": "", "collection": {"$id": 10}}]
        with patch("fillnel.steps.check_links._check_url") as mock_check:
            check_links.run(client, BROKEN_ID)
        mock_check.assert_not_called()
