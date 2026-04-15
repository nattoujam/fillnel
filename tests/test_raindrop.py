import json
from unittest.mock import MagicMock, patch, call

import pytest

from fillnel.services.raindrop import RaindropClient


@pytest.fixture
def client():
    return RaindropClient(token="test-token")


def mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


class TestGetTags:
    def test_returns_tag_names(self, client):
        resp = mock_response({"items": [{"_id": "AI"}, {"_id": "TypeScript"}]})
        with patch.object(client._session, "get", return_value=resp) as mock_get:
            tags = client.get_tags()

        assert tags == ["AI", "TypeScript"]
        mock_get.assert_called_once_with("https://api.raindrop.io/rest/v1/tags")

    def test_returns_empty_when_no_tags(self, client):
        resp = mock_response({"items": []})
        with patch.object(client._session, "get", return_value=resp):
            tags = client.get_tags()

        assert tags == []


class TestGetBookmarks:
    def test_fetches_all_pages(self, client):
        page0 = mock_response({"items": [{"_id": 1}] * 50})
        page1 = mock_response({"items": [{"_id": 2}] * 10})

        with patch.object(client._session, "get", side_effect=[page0, page1]) as mock_get:
            items = client.get_bookmarks()

        assert len(items) == 60
        assert mock_get.call_count == 2

    def test_filter_by_tag(self, client):
        resp = mock_response({"items": []})
        with patch.object(client._session, "get", return_value=resp) as mock_get:
            client.get_bookmarks(tag="推薦")

        _, kwargs = mock_get.call_args
        params = kwargs["params"]
        assert json.loads(params["search"]) == [{"key": "tag", "val": "推薦"}]

    def test_filter_by_not_tag(self, client):
        resp = mock_response({"items": []})
        with patch.object(client._session, "get", return_value=resp) as mock_get:
            client.get_bookmarks(not_tag="推薦")

        _, kwargs = mock_get.call_args
        params = kwargs["params"]
        assert json.loads(params["search"]) == [{"key": "notTag", "val": "推薦"}]


class TestCreateBookmark:
    def test_creates_successfully(self, client):
        resp = mock_response({}, status_code=200)
        with patch.object(client._session, "post", return_value=resp) as mock_post:
            client.create_bookmark({"link": "https://example.com", "title": "Test"})

        mock_post.assert_called_once()

    def test_ignores_url_already_exists(self, client):
        resp = mock_response({"errorMessage": "url_already_exists"}, status_code=400)
        with patch.object(client._session, "post", return_value=resp):
            # 例外が発生しないこと
            client.create_bookmark({"link": "https://example.com"})

    def test_raises_on_other_400(self, client):
        resp = mock_response({"errorMessage": "other_error"}, status_code=400)
        resp.raise_for_status.side_effect = Exception("400 error")
        with patch.object(client._session, "post", return_value=resp):
            with pytest.raises(Exception):
                client.create_bookmark({"link": "https://example.com"})


class TestUpdateBookmark:
    def test_calls_put_endpoint(self, client):
        resp = mock_response({})
        with patch.object(client._session, "put", return_value=resp) as mock_put:
            client.update_bookmark("123", {"tags": ["AI"]})

        mock_put.assert_called_once_with(
            "https://api.raindrop.io/rest/v1/raindrop/123",
            json={"tags": ["AI"]},
        )


class TestDeleteBookmarks:
    def test_calls_delete_with_ids(self, client):
        resp = mock_response({})
        with patch.object(client._session, "delete", return_value=resp) as mock_del:
            client.delete_bookmarks([1, 2, 3])

        mock_del.assert_called_once_with(
            "https://api.raindrop.io/rest/v1/raindrops",
            json={"ids": [1, 2, 3]},
        )

    def test_skips_empty_list(self, client):
        with patch.object(client._session, "delete") as mock_del:
            client.delete_bookmarks([])

        mock_del.assert_not_called()
