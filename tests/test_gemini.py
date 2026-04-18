import concurrent.futures
from unittest.mock import MagicMock, patch

import pytest
from google.genai.errors import ClientError, ServerError
from tenacity import RetryError

from fillnel.services.gemini import GeminiClient, _extract_articles, _extract_retry_delay, _parse_tags, _resolve_url
import fillnel.services.gemini as gemini_module


def make_client_error(code: int) -> ClientError:
    return ClientError(code, {"error": {"code": code, "message": "API key not valid", "status": "INVALID_ARGUMENT"}})

def make_server_error(code: int) -> ServerError:
    return ServerError(code, {"error": {"code": code, "message": "Internal error", "status": "INTERNAL"}})

def make_response(chunks: list[tuple[str, str]]) -> MagicMock:
    """(uri, title) のリストからモックレスポンスを生成する。"""
    response = MagicMock()
    response.text = "記事を収集しました。"
    grounding_chunks = []
    for uri, title in chunks:
        chunk = MagicMock()
        chunk.web.uri = uri
        chunk.web.title = title
        grounding_chunks.append(chunk)
    response.candidates[0].grounding_metadata.grounding_chunks = grounding_chunks
    return response


class TestExtractArticles:
    def test_extracts_urls_from_grounding_chunks(self, monkeypatch):
        monkeypatch.setattr(gemini_module, "_resolve_url", lambda url: url)
        response = make_response([
            ("https://a.com/article", "記事A"),
            ("https://b.com/article", "記事B"),
        ])
        result = _extract_articles(response)
        assert len(result) == 2
        assert result[0]["url"] == "https://a.com/article"
        assert result[1]["url"] == "https://b.com/article"

    def test_deduplicates_same_url(self, monkeypatch):
        monkeypatch.setattr(gemini_module, "_resolve_url", lambda url: url)
        response = make_response([
            ("https://a.com/article", "記事A"),
            ("https://a.com/article", "記事A"),  # 重複
            ("https://b.com/article", "記事B"),
        ])
        result = _extract_articles(response)
        assert len(result) == 2

    def test_resolves_redirect_urls(self, monkeypatch):
        redirect = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/xxx"
        real = "https://real-article.com/post"
        monkeypatch.setattr(gemini_module, "_resolve_url", lambda url: real if url == redirect else url)
        response = make_response([(redirect, "記事A")])
        result = _extract_articles(response)
        assert result[0]["url"] == real

    def test_returns_empty_when_no_grounding(self):
        response = MagicMock()
        response.text = "結果なし"
        response.candidates[0].grounding_metadata = None
        result = _extract_articles(response)
        assert result == []


class TestCollectArticles:
    def _make_client(self, chunks: list[tuple[str, str]]) -> GeminiClient:
        client = GeminiClient.__new__(GeminiClient)
        client._generate = MagicMock(return_value=make_response(chunks))
        return client

    def test_returns_articles_from_grounding(self, monkeypatch):
        monkeypatch.setattr(gemini_module, "_resolve_url", lambda url: url)
        client = self._make_client([("https://a.com", "記事A"), ("https://b.com", "記事B")])
        result = client.collect_articles(["AI", "TypeScript"])
        assert len(result) == 2
        assert result[0]["url"] == "https://a.com"

    def test_passes_topics_to_prompt(self, monkeypatch):
        monkeypatch.setattr(gemini_module, "_resolve_url", lambda url: url)
        client = self._make_client([])
        client.collect_articles(["AI", "TypeScript"])
        prompt = client._generate.call_args[0][0]
        assert "AI" in prompt
        assert "TypeScript" in prompt

    def test_uses_default_topic_when_empty(self, monkeypatch):
        monkeypatch.setattr(gemini_module, "_resolve_url", lambda url: url)
        client = self._make_client([])
        client.collect_articles([])
        prompt = client._generate.call_args[0][0]
        assert "一般技術" in prompt

    @pytest.mark.parametrize("code", [400, 403])
    def test_raises_runtime_error_on_invalid_api_key(self, code):
        client = GeminiClient.__new__(GeminiClient)
        client._generate = MagicMock(side_effect=make_client_error(code))
        with pytest.raises(RuntimeError, match="Gemini APIキーが無効です"):
            client.collect_articles(["AI"])

    def test_raises_runtime_error_on_rate_limit(self):
        client = GeminiClient.__new__(GeminiClient)
        client._generate = MagicMock(side_effect=make_client_error(429))
        with pytest.raises(RuntimeError, match="レートリミット"):
            client.collect_articles(["AI"])

    def test_raises_runtime_error_on_other_client_error(self):
        client = GeminiClient.__new__(GeminiClient)
        client._generate = MagicMock(side_effect=make_client_error(404))
        with pytest.raises(RuntimeError, match="Gemini APIエラー"):
            client.collect_articles(["AI"])

    def test_raises_runtime_error_after_server_error_retries(self):
        client = GeminiClient.__new__(GeminiClient)
        f = concurrent.futures.Future()
        f.set_exception(make_server_error(503))
        client._generate = MagicMock(side_effect=RetryError(f))

        with pytest.raises(RuntimeError, match="サーバーエラー"):
            client.collect_articles(["AI"])


class TestExtractRetryDelay:
    def test_parses_retry_delay_from_error(self):
        e = ClientError(429, {"error": {"code": 429, "message": "", "status": "RESOURCE_EXHAUSTED", "details": [
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "57s"},
        ]}})
        assert _extract_retry_delay(e) == 62.0  # 57 + 5

    def test_returns_default_when_no_detail(self):
        e = ClientError(429, {"error": {"code": 429, "message": "", "status": "RESOURCE_EXHAUSTED", "details": []}})
        assert _extract_retry_delay(e) == 65.0


class TestParseTags:
    def _resp(self, text: str) -> MagicMock:
        r = MagicMock()
        r.text = text
        return r

    def test_parses_raw_json_array(self):
        result = _parse_tags(self._resp('["AI", "TypeScript", "自己ホスト"]'))
        assert result == ["AI", "TypeScript", "自己ホスト"]

    def test_parses_markdown_code_block(self):
        result = _parse_tags(self._resp('```json\n["AI", "TypeScript"]\n```'))
        assert result == ["AI", "TypeScript"]

    def test_returns_empty_on_invalid_json(self):
        result = _parse_tags(self._resp("タグは見つかりませんでした"))
        assert result == []


class TestEstimateTags:
    def _make_client(self, response_text: str) -> GeminiClient:
        client = GeminiClient.__new__(GeminiClient)
        resp = MagicMock()
        resp.text = response_text
        client._generate_text = MagicMock(return_value=resp)
        return client

    def test_returns_parsed_tags(self):
        client = self._make_client('["AI", "機械学習"]')
        result = client.estimate_tags(
            title="AIの最新動向",
            url="https://example.com/ai",
            existing_tags=["AI", "TypeScript"],
        )
        assert result == ["AI", "機械学習"]

    def test_includes_title_and_url_in_prompt(self):
        client = self._make_client('["AI"]')
        client.estimate_tags(
            title="AIの最新動向",
            url="https://example.com/ai",
            existing_tags=[],
        )
        prompt = client._generate_text.call_args[0][0]
        assert "AIの最新動向" in prompt
        assert "https://example.com/ai" in prompt

    def test_returns_empty_on_client_error(self):
        client = GeminiClient.__new__(GeminiClient)
        client._generate_text = MagicMock(side_effect=make_client_error(403))
        result = client.estimate_tags("title", "https://example.com", [])
        assert result == []

    def test_returns_empty_on_retry_error(self):
        client = GeminiClient.__new__(GeminiClient)
        f = concurrent.futures.Future()
        f.set_exception(make_server_error(503))
        client._generate_text = MagicMock(side_effect=RetryError(f))
        result = client.estimate_tags("title", "https://example.com", [])
        assert result == []

    def test_retries_on_429_and_succeeds(self):
        client = GeminiClient.__new__(GeminiClient)
        resp = MagicMock()
        resp.text = '["AI"]'
        client._generate_text = MagicMock(side_effect=[
            make_client_error(429),
            resp,
        ])
        with patch("fillnel.services.gemini.time.sleep"):
            result = client.estimate_tags("title", "https://example.com", [])
        assert result == ["AI"]
        assert client._generate_text.call_count == 2

    def test_returns_empty_after_max_429_retries(self):
        client = GeminiClient.__new__(GeminiClient)
        client._generate_text = MagicMock(side_effect=make_client_error(429))
        with patch("fillnel.services.gemini.time.sleep"):
            result = client.estimate_tags("title", "https://example.com", [])
        assert result == []
        assert client._generate_text.call_count == 3
