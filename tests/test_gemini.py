import concurrent.futures
from unittest.mock import MagicMock

import pytest
from google.genai.errors import ClientError, ServerError
from tenacity import RetryError

from fillnel.services.gemini import GeminiClient, _extract_articles, _resolve_url
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
