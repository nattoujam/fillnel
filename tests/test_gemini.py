import concurrent.futures
from unittest.mock import MagicMock, patch

import pytest
from google.genai.errors import ClientError, ServerError
from tenacity import RetryError

from fillnel.services.gemini import (
    GeminiClient, _extract_articles, _extract_retry_delay, _parse_tags, _resolve_url,
    _uri_at_char_pos, _uri_by_chunk_title, _build_position_map,
    _parse_articles_with_grounding, _extract_from_chunks,
)
import fillnel.services.gemini as gemini_module


@pytest.fixture
def gemini_client(monkeypatch):
    """genai.Client をモックした GeminiClient を生成する。__init__ を通す。"""
    def _make():
        mock_genai = MagicMock()
        monkeypatch.setattr("fillnel.services.gemini.genai", mock_genai)
        client = GeminiClient("test-key")
        return client, mock_genai
    return _make


def make_client_error(code: int) -> ClientError:
    return ClientError(code, {"error": {"code": code, "message": "API key not valid", "status": "INVALID_ARGUMENT"}})

def make_server_error(code: int) -> ServerError:
    return ServerError(code, {"error": {"code": code, "message": "Internal error", "status": "INTERNAL"}})

def make_structured_text(articles: list[tuple[str, str]]) -> str:
    """(title, summary) のリストから構造化テキストを生成する。"""
    lines = []
    for title, summary in articles:
        lines.append(f"タイトル: {title}")
        lines.append(f"要約: {summary}")
        lines.append("")
    return "\n".join(lines)

def make_support(seg_text: str, chunk_indices: list[int], scores: list[float]) -> MagicMock:
    support = MagicMock()
    support.segment.text = seg_text
    support.grounding_chunk_indices = chunk_indices
    support.confidence_scores = scores
    return support

def make_response(
    chunks: list[tuple[str, str]],
    text: str = "記事を収集しました。",
    supports: list[tuple[str, list[int], list[float]]] | None = None,
) -> MagicMock:
    """(uri, title) チャンクリストと省略可能なsupportsからモックレスポンスを生成する。"""
    response = MagicMock()
    response.text = text
    grounding_chunks = []
    for uri, title in chunks:
        chunk = MagicMock()
        chunk.web.uri = uri
        chunk.web.title = title
        grounding_chunks.append(chunk)
    response.candidates[0].grounding_metadata.grounding_chunks = grounding_chunks
    grounding_supports = [make_support(*s) for s in supports] if supports else []
    response.candidates[0].grounding_metadata.grounding_supports = grounding_supports
    return response


def make_position_support(start: int, end: int, chunk_idx: int) -> MagicMock:
    """バイト位置ベースのsupportモックを生成する。"""
    support = MagicMock()
    support.segment.start_index = start
    support.segment.end_index = end
    support.grounding_chunk_indices = [chunk_idx]
    support.confidence_scores = [1.0]
    return support

def make_chunk(uri: str, title: str = "") -> MagicMock:
    chunk = MagicMock()
    chunk.web.uri = uri
    chunk.web.title = title
    return chunk


class TestBuildPositionMap:
    def test_builds_mapping_from_supports(self):
        chunks = [make_chunk("https://a.com/1"), make_chunk("https://b.com/2")]
        supports = [make_position_support(0, 10, 0), make_position_support(10, 20, 1)]
        mappings = _build_position_map("", supports, chunks)
        assert len(mappings) == 2

    def test_sorts_by_segment_size_ascending(self):
        """小さいセグメントが先頭に来る（優先度高）。"""
        chunks = [make_chunk("https://a.com/1"), make_chunk("https://b.com/2")]
        supports = [
            make_position_support(0, 100, 0),  # 大きいセグメント
            make_position_support(0, 10, 1),   # 小さいセグメント
        ]
        mappings = _build_position_map("", supports, chunks)
        assert mappings[0][2] == "https://b.com/2"  # 小さい方が先

    def test_skips_empty_segment(self):
        chunks = [make_chunk("https://a.com/1")]
        supports = [make_position_support(5, 5, 0)]  # start == end
        mappings = _build_position_map("", supports, chunks)
        assert mappings == []


class TestUriAtCharPos:
    def test_returns_uri_for_covered_position(self):
        text = "タイトル: 記事A\n要約: 要約A\n"
        pos = text.find("記事A")
        byte_pos = len(text[:pos].encode("utf-8"))
        mappings = [(byte_pos, byte_pos + 50, "https://a.com/article/1")]
        result = _uri_at_char_pos(pos, text, mappings)
        assert result == "https://a.com/article/1"

    def test_returns_smallest_segment_when_overlapping(self):
        text = "タイトル: 記事A\n要約: 要約A\n"
        pos = text.find("記事A")
        byte_pos = len(text[:pos].encode("utf-8"))
        mappings = [
            (byte_pos, byte_pos + 100, "https://big.com/1"),
            (byte_pos, byte_pos + 10, "https://small.com/2"),
        ]
        mappings.sort(key=lambda m: m[1] - m[0])
        result = _uri_at_char_pos(pos, text, mappings)
        assert result == "https://small.com/2"

    def test_returns_none_when_no_mapping_covers_pos(self):
        text = "タイトル: 記事A\n"
        result = _uri_at_char_pos(0, text, [(100, 200, "https://a.com/1")])
        assert result is None


class TestUriByChunkTitle:
    def test_matches_when_article_title_in_chunk_title(self):
        chunks = [make_chunk("https://a.com/1", "記事A の詳細解説")]
        result = _uri_by_chunk_title("記事A", chunks, exclude=set())
        assert result == "https://a.com/1"

    def test_matches_when_chunk_title_in_article_title(self):
        chunks = [make_chunk("https://a.com/1", "記事A")]
        result = _uri_by_chunk_title("記事A の詳細解説", chunks, exclude=set())
        assert result == "https://a.com/1"

    def test_skips_excluded_uris(self):
        chunks = [make_chunk("https://a.com/1", "記事A")]
        result = _uri_by_chunk_title("記事A", chunks, exclude={"https://a.com/1"})
        assert result is None

    def test_returns_none_when_no_match(self):
        chunks = [make_chunk("https://a.com/1", "全く別の記事")]
        result = _uri_by_chunk_title("記事B", chunks, exclude=set())
        assert result is None


def make_candidate_with_position_supports(
    text: str,
    chunk_uris: list[str],
    chunk_titles: list[str],
    article_titles: list[str],
) -> MagicMock:
    """各記事タイトルのバイト位置をsupport.start_index/end_indexに設定したcandidateを生成する。"""
    candidate = MagicMock()
    chunks = [make_chunk(uri, title) for uri, title in zip(chunk_uris, chunk_titles)]
    candidate.grounding_metadata.grounding_chunks = chunks

    supports = []
    for i, title in enumerate(article_titles):
        if i >= len(chunk_uris):
            break
        pos = text.find(title)
        if pos == -1:
            continue
        byte_start = len(text[:pos].encode("utf-8"))
        byte_end = byte_start + len(title.encode("utf-8"))
        sup = MagicMock()
        sup.segment.start_index = byte_start
        sup.segment.end_index = byte_end
        sup.grounding_chunk_indices = [i]
        sup.confidence_scores = [1.0]
        supports.append(sup)
    candidate.grounding_metadata.grounding_supports = supports
    return candidate


class TestParseArticlesWithGrounding:
    def test_extracts_title_summary_url(self):
        text = make_structured_text([("記事A", "要約A"), ("記事B", "要約B")])
        candidate = make_candidate_with_position_supports(
            text,
            chunk_uris=["https://a.com/article/1", "https://b.com/article/2"],
            chunk_titles=["記事A", "記事B"],
            article_titles=["記事A", "記事B"],
        )
        result = _parse_articles_with_grounding(text, candidate)
        assert len(result) == 2
        assert result[0] == {"title": "記事A", "url": "https://a.com/article/1", "summary": "要約A"}
        assert result[1] == {"title": "記事B", "url": "https://b.com/article/2", "summary": "要約B"}

    def test_deduplicates_urls_via_chunk_title_fallback(self):
        """位置マッチで同じURLになった場合、chunk.web.titleで別URLに振り直す。"""
        text = make_structured_text([("記事A", "要約A"), ("記事B", "要約B")])
        candidate = MagicMock()
        candidate.grounding_metadata.grounding_chunks = [
            make_chunk("https://a.com/article/1", "記事A"),
            make_chunk("https://b.com/article/2", "記事B"),
        ]
        # 両方の記事が同じchunk(0)にマッチする大きなセグメント
        sup = MagicMock()
        sup.segment.start_index = 0
        sup.segment.end_index = len(text.encode("utf-8"))
        sup.grounding_chunk_indices = [0]
        sup.confidence_scores = [1.0]
        candidate.grounding_metadata.grounding_supports = [sup]

        result = _parse_articles_with_grounding(text, candidate)
        urls = [a["url"] for a in result]
        assert len(set(urls)) == len(urls)  # URL重複なし

    def test_returns_empty_when_supports_empty(self):
        text = make_structured_text([("記事A", "要約A")])
        candidate = MagicMock()
        candidate.grounding_metadata.grounding_chunks = []
        candidate.grounding_metadata.grounding_supports = []
        result = _parse_articles_with_grounding(text, candidate)
        assert result == []

    def test_returns_empty_when_no_article_format(self):
        candidate = MagicMock()
        candidate.grounding_metadata.grounding_chunks = []
        candidate.grounding_metadata.grounding_supports = []
        result = _parse_articles_with_grounding("記事を収集しました。", candidate)
        assert result == []


class TestExtractArticles:
    def test_extracts_articles_via_grounding_supports(self):
        text = make_structured_text([("記事A", "要約A")])
        candidate = make_candidate_with_position_supports(
            text,
            chunk_uris=["https://a.com/article/1"],
            chunk_titles=["記事A"],
            article_titles=["記事A"],
        )
        response = MagicMock()
        response.text = text
        response.candidates = [candidate]
        result = _extract_articles(response)
        assert len(result) == 1
        assert result[0]["url"] == "https://a.com/article/1"
        assert result[0]["title"] == "記事A"
        assert result[0]["summary"] == "要約A"

    def test_falls_back_to_chunks_when_supports_empty(self, monkeypatch):
        monkeypatch.setattr(gemini_module, "_resolve_url", lambda url: url)
        response = make_response(
            chunks=[("https://a.com/article/1", ""), ("https://b.com/article/2", "")],
            text="記事を収集しました。",  # 構造化フォーマットなし
            supports=[],
        )
        result = _extract_articles(response)
        assert len(result) == 2
        assert result[0]["url"] == "https://a.com/article/1"

    def test_fallback_skips_root_domain_urls(self, monkeypatch):
        monkeypatch.setattr(gemini_module, "_resolve_url", lambda url: "https://qiita.com/")
        response = make_response(
            chunks=[("https://vertexaisearch.cloud.google.com/redirect/xxx", "")],
            text="記事を収集しました。",
            supports=[],
        )
        result = _extract_articles(response)
        assert result == []

    def test_returns_empty_when_no_grounding(self):
        response = MagicMock()
        response.text = "結果なし"
        response.candidates[0].grounding_metadata = None
        result = _extract_articles(response)
        assert result == []


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
    def _make_client(self, gemini_client, response: MagicMock) -> GeminiClient:
        client, mock_genai = gemini_client()
        client._generate = MagicMock(return_value=response)
        return client

    def test_returns_articles_from_grounding_supports(self, gemini_client):
        text = make_structured_text([("記事A", "要約A"), ("記事B", "要約B")])
        candidate = make_candidate_with_position_supports(
            text,
            chunk_uris=["https://a.com/article/1", "https://b.com/post/2"],
            chunk_titles=["記事A", "記事B"],
            article_titles=["記事A", "記事B"],
        )
        response = MagicMock()
        response.text = text
        response.candidates = [candidate]
        client = self._make_client(gemini_client, response)
        result = client.collect_articles({"AI": 6.0, "TypeScript": 4.0}, [])
        assert len(result) == 2
        assert result[0]["url"] == "https://a.com/article/1"

    def test_passes_topics_to_prompt(self, gemini_client):
        response = make_response(chunks=[], supports=[])
        client = self._make_client(gemini_client, response)
        client.collect_articles({"AI": 6.0, "TypeScript": 4.0}, [])
        prompt = client._generate.call_args[0][0]
        assert "AI" in prompt
        assert "TypeScript" in prompt

    def test_passes_domains_to_prompt(self, gemini_client):
        response = make_response(chunks=[], supports=[])
        client = self._make_client(gemini_client, response)
        client.collect_articles({"AI": 6.0}, ["zenn.dev", "qiita.com"])
        prompt = client._generate.call_args[0][0]
        assert "zenn.dev" in prompt
        assert "qiita.com" in prompt

    def test_uses_default_topic_when_empty(self, gemini_client):
        response = make_response(chunks=[], supports=[])
        client = self._make_client(gemini_client, response)
        client.collect_articles({}, [])
        prompt = client._generate.call_args[0][0]
        assert "一般技術" in prompt

    def test_prompt_does_not_contain_url_field(self, gemini_client):
        """プロンプトにURL出力指示が含まれないことを確認する。"""
        response = make_response(chunks=[], supports=[])
        client = self._make_client(gemini_client, response)
        client.collect_articles({"AI": 6.0}, [])
        prompt = client._generate.call_args[0][0]
        assert "URL:" not in prompt

    @pytest.mark.parametrize("code", [400, 403])
    def test_raises_runtime_error_on_invalid_api_key(self, code, gemini_client):
        client, _ = gemini_client()
        client._generate = MagicMock(side_effect=make_client_error(code))
        with pytest.raises(RuntimeError, match="Gemini APIキーが無効です"):
            client.collect_articles({"AI": 6.0}, [])

    def test_raises_runtime_error_on_rate_limit(self, gemini_client):
        client, _ = gemini_client()
        client._generate = MagicMock(side_effect=make_client_error(429))
        with pytest.raises(RuntimeError, match="レートリミット"):
            client.collect_articles({"AI": 6.0}, [])

    def test_raises_runtime_error_on_other_client_error(self, gemini_client):
        client, _ = gemini_client()
        client._generate = MagicMock(side_effect=make_client_error(404))
        with pytest.raises(RuntimeError, match="Gemini APIエラー"):
            client.collect_articles({"AI": 6.0}, [])

    def test_raises_runtime_error_after_server_error_retries(self, gemini_client):
        client, _ = gemini_client()
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
    def _make_client(self, gemini_client, response_text: str) -> GeminiClient:
        client, mock_genai = gemini_client()
        resp = MagicMock()
        resp.text = response_text
        client._generate_text = MagicMock(return_value=resp)
        return client

    def test_returns_parsed_tags(self, gemini_client):
        client = self._make_client(gemini_client, '["AI", "機械学習"]')
        result = client.estimate_tags(
            title="AIの最新動向",
            url="https://example.com/ai",
            existing_tags=["AI", "TypeScript"],
        )
        assert result == ["AI", "機械学習"]

    def test_includes_title_and_url_in_prompt(self, gemini_client):
        client = self._make_client(gemini_client, '["AI"]')
        client.estimate_tags(
            title="AIの最新動向",
            url="https://example.com/ai",
            existing_tags=[],
        )
        prompt = client._generate_text.call_args[0][0]
        assert "AIの最新動向" in prompt
        assert "https://example.com/ai" in prompt

    def test_returns_empty_on_client_error(self, gemini_client):
        client, _ = gemini_client()
        client._generate_text = MagicMock(side_effect=make_client_error(403))
        result = client.estimate_tags("title", "https://example.com", [])
        assert result == []

    def test_returns_empty_on_retry_error(self, gemini_client):
        client, _ = gemini_client()
        f = concurrent.futures.Future()
        f.set_exception(make_server_error(503))
        client._generate_text = MagicMock(side_effect=RetryError(f))
        result = client.estimate_tags("title", "https://example.com", [])
        assert result == []

    def test_retries_on_429_and_succeeds(self, gemini_client):
        client, _ = gemini_client()
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

    def test_returns_empty_after_max_429_retries(self, gemini_client):
        client, _ = gemini_client()
        client._generate_text = MagicMock(side_effect=make_client_error(429))
        with patch("fillnel.services.gemini.time.sleep"):
            result = client.estimate_tags("title", "https://example.com", [])
        assert result == []
        assert client._generate_text.call_count == 3


class TestEmbedTexts:
    def test_single_batch_under_limit(self, gemini_client):
        """100件以内は1バッチで処理。"""
        client, mock_genai = gemini_client()
        texts = [f"text{i}" for i in range(50)]
        mock_embeddings = [MagicMock(values=[float(i), 0.0, 0.0]) for i in range(50)]
        mock_genai.Client.return_value.models.embed_content.return_value = MagicMock(embeddings=mock_embeddings)

        with patch("fillnel.services.gemini.time.sleep"):
            result = client.embed_texts(texts)

        assert len(result) == 50
        mock_genai.Client.return_value.models.embed_content.assert_called_once()
        args = mock_genai.Client.return_value.models.embed_content.call_args
        assert args.kwargs["contents"] == texts

    def test_multi_batch_splits_into_chunks(self, gemini_client):
        """100件超えは100件ずつ分割して呼び出す。"""
        client, mock_genai = gemini_client()
        texts = [f"text{i}" for i in range(250)]

        call_count = [0]

        def side_effect(*, contents, **kwargs):
            call_count[0] += 1
            n = len(contents)
            embeddings = [MagicMock(values=[float(i), 0.0, 0.0]) for i in range(n)]
            return MagicMock(embeddings=embeddings)

        mock_genai.Client.return_value.models.embed_content.side_effect = side_effect

        with patch("fillnel.services.gemini.time.sleep"):
            result = client.embed_texts(texts)

        assert len(result) == 250
        assert call_count[0] == 3  # 100+100+50

    def test_result_order_preserved(self, gemini_client):
        """複数バッチでも結果の順序は原文書の順序と一致する。"""
        client, mock_genai = gemini_client()
        texts = [f"text{i}" for i in range(150)]

        global_idx = [0]  # mutable counter

        def side_effect(*, contents, **kwargs):
            embeddings = [
                MagicMock(values=[float(global_idx[0] + i), 0.0, 0.0])
                for i in range(len(contents))
            ]
            global_idx[0] += len(contents)
            return MagicMock(embeddings=embeddings)

        mock_genai.Client.return_value.models.embed_content.side_effect = side_effect

        with patch("fillnel.services.gemini.time.sleep"):
            result = client.embed_texts(texts)

        for i, vec in enumerate(result):
            assert vec[0] == float(i)


class TestCreateGeminiClient:
    def test_creates_client_with_api_key(self, monkeypatch):
        """create_gemini_client が api_key を渡して GeminiClient を生成する。"""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        mock_client = MagicMock()
        monkeypatch.setattr("fillnel.services.gemini.genai.Client", mock_client)

        from fillnel.services.gemini import create_gemini_client

        client = create_gemini_client()

        mock_client.assert_called_once_with(api_key="test-key")
        assert isinstance(client, GeminiClient)
        assert client._client is mock_client.return_value
