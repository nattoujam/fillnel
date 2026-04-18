import concurrent.futures
from unittest.mock import MagicMock, patch

import pytest
from google.genai.errors import ClientError, ServerError
from tenacity import RetryError

from fillnel.services.gemini import (
    GeminiClient, _extract_articles, _extract_retry_delay, _parse_tags, _resolve_url,
    _parse_articles_from_text, _extract_from_chunks,
)
import fillnel.services.gemini as gemini_module


def make_client_error(code: int) -> ClientError:
    return ClientError(code, {"error": {"code": code, "message": "API key not valid", "status": "INVALID_ARGUMENT"}})

def make_server_error(code: int) -> ServerError:
    return ServerError(code, {"error": {"code": code, "message": "Internal error", "status": "INTERNAL"}})

def make_structured_text(articles: list[tuple[str, str, str]]) -> str:
    """(title, url, summary) のリストから構造化テキストを生成する。"""
    lines = []
    for title, url, summary in articles:
        lines.append(f"タイトル: {title}")
        lines.append(f"URL: {url}")
        lines.append(f"要約: {summary}")
        lines.append("")
    return "\n".join(lines)

def make_response(chunks: list[tuple[str, str]], text: str = "記事を収集しました。") -> MagicMock:
    """(uri, title) のリストからモックレスポンスを生成する。"""
    response = MagicMock()
    response.text = text
    grounding_chunks = []
    for uri, title in chunks:
        chunk = MagicMock()
        chunk.web.uri = uri
        chunk.web.title = title
        grounding_chunks.append(chunk)
    response.candidates[0].grounding_metadata.grounding_chunks = grounding_chunks
    return response


class TestExtractArticles:
    def test_extracts_articles_from_text(self, monkeypatch):
        monkeypatch.setattr(gemini_module, "_resolve_url", lambda url: url)
        text = make_structured_text([
            ("記事A", "https://a.com/article/1", "要約A"),
            ("記事B", "https://b.com/article/2", "要約B"),
        ])
        response = make_response(
            [("https://a.com/article/1", ""), ("https://b.com/article/2", "")],
            text=text,
        )
        result = _extract_articles(response)
        assert len(result) == 2
        assert result[0]["url"] == "https://a.com/article/1"
        assert result[0]["title"] == "記事A"
        assert result[0]["summary"] == "要約A"

    def test_validates_domain_against_grounding(self, monkeypatch):
        monkeypatch.setattr(gemini_module, "_resolve_url", lambda url: url)
        text = make_structured_text([
            ("正規記事", "https://a.com/article/1", "要約A"),
            ("ハルシネーション記事", "https://fake.com/article/99", "要約B"),
        ])
        # grounding_chunks には a.com しかない
        response = make_response([("https://a.com/article/1", "")], text=text)
        result = _extract_articles(response)
        assert len(result) == 1
        assert result[0]["url"] == "https://a.com/article/1"

    def test_falls_back_to_chunks_when_text_unparseable(self, monkeypatch):
        monkeypatch.setattr(gemini_module, "_resolve_url", lambda url: url)
        response = make_response(
            [("https://a.com/article/1", ""), ("https://b.com/article/2", "")],
            text="記事を収集しました。",  # 構造化フォーマットなし
        )
        result = _extract_articles(response)
        assert len(result) == 2
        assert result[0]["url"] == "https://a.com/article/1"

    def test_fallback_skips_root_domain_urls(self, monkeypatch):
        monkeypatch.setattr(gemini_module, "_resolve_url", lambda url: "https://qiita.com/")
        response = make_response(
            [("https://vertexaisearch.cloud.google.com/redirect/xxx", "")],
            text="記事を収集しました。",
        )
        result = _extract_articles(response)
        assert result == []

    def test_returns_empty_when_no_grounding(self):
        response = MagicMock()
        response.text = "結果なし"
        response.candidates[0].grounding_metadata = None
        result = _extract_articles(response)
        assert result == []


class TestParseArticlesFromText:
    def test_strips_trailing_punctuation_from_url(self):
        text = "タイトル: 記事A\nURL: https://a.com/article/1.\n要約: 要約A"
        result = _parse_articles_from_text(text, {"a.com"})
        assert result[0]["url"] == "https://a.com/article/1"

    def test_skips_when_no_allowed_domains(self):
        text = make_structured_text([("記事A", "https://a.com/article/1", "要約A")])
        # allowed_domains が空の場合はドメイン検証をスキップ
        result = _parse_articles_from_text(text, set())
        assert len(result) == 1


class TestExtractFromChunks:
    def test_deduplicates_same_uri(self, monkeypatch):
        monkeypatch.setattr(gemini_module, "_resolve_url", lambda url: url)
        response = make_response([
            ("https://a.com/article/1", ""),
            ("https://a.com/article/1", ""),  # 重複
            ("https://b.com/article/2", ""),
        ])
        result = _extract_from_chunks(response.candidates[0])
        assert len(result) == 2

    def test_skips_root_domain_urls(self, monkeypatch):
        monkeypatch.setattr(gemini_module, "_resolve_url", lambda url: "https://qiita.com/")
        response = make_response([("https://vertexaisearch.cloud.google.com/redirect/xxx", "")])
        result = _extract_from_chunks(response.candidates[0])
        assert result == []


class TestCollectArticles:
    def _make_client(self, chunks: list[tuple[str, str]]) -> GeminiClient:
        client = GeminiClient.__new__(GeminiClient)
        client._generate = MagicMock(return_value=make_response(chunks))
        return client

    def test_returns_articles_from_grounding(self, monkeypatch):
        monkeypatch.setattr(gemini_module, "_resolve_url", lambda url: url)
        client = self._make_client([("https://a.com/article/1", "記事A"), ("https://b.com/post/2", "記事B")])
        result = client.collect_articles({"AI": 6.0, "TypeScript": 4.0}, [])
        assert len(result) == 2
        assert result[0]["url"] == "https://a.com/article/1"

    def test_passes_topics_to_prompt(self, monkeypatch):
        monkeypatch.setattr(gemini_module, "_resolve_url", lambda url: url)
        client = self._make_client([])
        client.collect_articles({"AI": 6.0, "TypeScript": 4.0}, [])
        prompt = client._generate.call_args[0][0]
        assert "AI" in prompt
        assert "TypeScript" in prompt

    def test_passes_domains_to_prompt(self, monkeypatch):
        monkeypatch.setattr(gemini_module, "_resolve_url", lambda url: url)
        client = self._make_client([])
        client.collect_articles({"AI": 6.0}, ["zenn.dev", "qiita.com"])
        prompt = client._generate.call_args[0][0]
        assert "zenn.dev" in prompt
        assert "qiita.com" in prompt

    def test_uses_default_topic_when_empty(self, monkeypatch):
        monkeypatch.setattr(gemini_module, "_resolve_url", lambda url: url)
        client = self._make_client([])
        client.collect_articles({}, [])
        prompt = client._generate.call_args[0][0]
        assert "一般技術" in prompt

    @pytest.mark.parametrize("code", [400, 403])
    def test_raises_runtime_error_on_invalid_api_key(self, code):
        client = GeminiClient.__new__(GeminiClient)
        client._generate = MagicMock(side_effect=make_client_error(code))
        with pytest.raises(RuntimeError, match="Gemini APIキーが無効です"):
            client.collect_articles({"AI": 6.0}, [])

    def test_raises_runtime_error_on_rate_limit(self):
        client = GeminiClient.__new__(GeminiClient)
        client._generate = MagicMock(side_effect=make_client_error(429))
        with pytest.raises(RuntimeError, match="レートリミット"):
            client.collect_articles({"AI": 6.0}, [])

    def test_raises_runtime_error_on_other_client_error(self):
        client = GeminiClient.__new__(GeminiClient)
        client._generate = MagicMock(side_effect=make_client_error(404))
        with pytest.raises(RuntimeError, match="Gemini APIエラー"):
            client.collect_articles({"AI": 6.0}, [])

    def test_raises_runtime_error_after_server_error_retries(self):
        client = GeminiClient.__new__(GeminiClient)
        f = concurrent.futures.Future()
        f.set_exception(make_server_error(503))
        client._generate = MagicMock(side_effect=RetryError(f))

        with pytest.raises(RuntimeError, match="サーバーエラー"):
            client.collect_articles({"AI": 6.0}, [])


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
