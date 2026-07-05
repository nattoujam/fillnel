import json
import logging
import os
import re
import time

import requests
from urllib.parse import urlparse
from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, RetryError

logger = logging.getLogger(__name__)

MODEL = "gemini-3.1-flash-lite"
TAG_MODEL = "gemini-3.1-flash-lite"
EMBED_MODEL = "gemini-embedding-001"

FILTER_PROMPT = """\
以下の記事候補から、ユーザーの興味に合う高品質な記事を最大5件選んでください。
{favorites_section}
記事候補:
{candidates_section}
優先条件（以下に該当する記事を優先すること）：
- 技術的な実装・設計・考察を含む記事
- 著者の一次情報・独自検証・実体験にもとづく記事
- 具体的なコード・手順・数値を含む記事

除外条件（以下に該当する記事は絶対に選ばないこと）：
- AIが自動生成した記事
- ランキング・おすすめ商品・まとめ系の記事（独自の考察がないもの）
- 新製品発表・リリース情報のみのニュース記事
- ガジェット・デバイス紹介記事
- 業務効率化・ライフハック系の浅い記事
- YouTube・Vimeoなどの動画コンテンツ

選んだ記事の番号をカンマ区切りで返してください（例: 1, 3, 5）。
数字のみで返してください。
"""

COLLECT_PROMPT = """\
以下の情報をもとに、ユーザーの興味に合った最近の技術記事を5件探してください。

興味トピック（重み順）:
{topics}
{domains_section}
優先条件（以下に該当する記事を優先すること）：
- 技術的な実装・設計・考察を含む記事
- 著者の一次情報・独自検証・実体験にもとづく記事
- 具体的なコード・手順・数値を含む記事

除外条件（以下に該当する記事は絶対に選ばないこと）：
- AIが自動生成した記事
- ランキング・おすすめ商品・まとめ系の記事（独自の考察がないもの）
- 新製品発表・リリース情報のみのニュース記事
- ガジェット・デバイス紹介記事
- 業務効率化・ライフハック系の浅い記事
- YouTube・Vimeoなどの動画コンテンツ

{favorites_section}各記事を以下の形式で出力してください：

タイトル: <記事タイトル>
要約: <50字以内の日本語要約>
"""

SUMMARIZE_PROMPT = """\
以下の記事を50字以内の日本語で要約してください。

タイトル: {title}
URL: {url}

要約のみを返してください（説明不要）。
"""

ESTIMATE_TAGS_PROMPT = """\
既存タグ: {existing_tags}

以下の記事のトピックを表すタグを3〜8個返してください。
記事タイトル: {title}
記事URL: {url}

ルール：
- 既存タグに近いものがあれば必ずそちらを使う
- 既存タグにない概念の場合のみ新しいタグを作る
- 新しいタグは既存タグと重複・類似しないよう注意する
- タグは日本語に統一する（ただし固有名詞・技術名はそのまま使う）
- プログラミング・技術系の記事の場合は以下を優先的にタグとして抽出する：
  - 使用言語（例: Python, TypeScript, Rust, Go）
  - フレームワーク・ライブラリ（例: React, FastAPI, LangChain）
  - ツール・プラットフォーム（例: Docker, Kubernetes, GitHub Actions）

JSON配列のみで返してください: ["タグ1", "タグ2", ...]
"""

_retry_server_error = retry(
    retry=retry_if_exception_type(ServerError),
    wait=wait_exponential(multiplier=1, min=5, max=60),
    stop=stop_after_attempt(3),
    before_sleep=lambda rs: logger.warning(
        f"Gemini APIサーバーエラー、リトライします ({rs.attempt_number}/3)... "
        f"code={rs.outcome.exception().code} message={rs.outcome.exception().message}"
    ),
)


def _resolve_url(url: str) -> str:
    """リダイレクトURLを辿って最終URLを返す。失敗時は元のURLを返す。"""
    try:
        resp = requests.head(url, allow_redirects=True, timeout=5)
        return resp.url
    except Exception:
        return url


_ARTICLE_PATTERN = re.compile(
    r"タイトル[:：]\s*(.+)\n"
    r"要約[:：]\s*(.+)"
)


def _is_root_url(url: str) -> bool:
    """ドメインのトップページ（記事URLでない）かどうかを判定する。"""
    parsed = urlparse(url)
    return parsed.path in ("", "/") and not parsed.query


def _build_position_map(text: str, supports, chunks: list) -> list[tuple[int, int, str]]:
    """grounding_supportsからバイト位置範囲→chunk URI のマッピングリストを返す。
    同一位置に複数のsupportが重なる場合は最小セグメントを優先するため、サイズ昇順でソートする。
    """
    mappings = []
    for support in supports:
        seg = support.segment
        start = seg.start_index or 0
        end = seg.end_index or 0
        if start >= end or not support.grounding_chunk_indices:
            continue
        scores = support.confidence_scores or [1.0] * len(support.grounding_chunk_indices)
        best_i = max(range(len(scores)), key=lambda i: scores[i])
        chunk_idx = support.grounding_chunk_indices[best_i]
        if chunk_idx < len(chunks) and chunks[chunk_idx].web and chunks[chunk_idx].web.uri:
            mappings.append((start, end, chunks[chunk_idx].web.uri))
    mappings.sort(key=lambda m: m[1] - m[0])  # セグメントサイズ昇順（小さい=具体的）
    return mappings


def _uri_at_char_pos(char_pos: int, text: str, mappings: list[tuple[int, int, str]]) -> str | None:
    """文字位置に対応するchunk URIを最小セグメントから返す。"""
    byte_pos = len(text[:char_pos].encode("utf-8"))
    for start, end, uri in mappings:
        if start <= byte_pos < end:
            return uri
    return None


def _uri_by_chunk_title(title: str, chunks: list, exclude: set[str]) -> str | None:
    """chunk.web.titleとの包含関係でURIを返す（重複解消フォールバック）。"""
    for chunk in chunks:
        if not (chunk.web and chunk.web.uri and chunk.web.title):
            continue
        if chunk.web.uri in exclude:
            continue
        ct = chunk.web.title
        if title in ct or ct in title:
            return chunk.web.uri
    return None


def _parse_articles_with_grounding(text: str, candidate) -> list[dict]:
    """grounding_supportsを使ってタイトル・要約・URLを抽出する。
    位置ベースマッチ（優先）→ chunk.web.titleマッチ（重複・未発見時）の順で解決する。
    """
    chunks = list(candidate.grounding_metadata.grounding_chunks) \
        if candidate.grounding_metadata and candidate.grounding_metadata.grounding_chunks else []
    supports = list(candidate.grounding_metadata.grounding_supports) \
        if candidate.grounding_metadata and candidate.grounding_metadata.grounding_supports else []

    logger.debug(f"grounding_chunks: {len(chunks)} 件, grounding_supports: {len(supports)} 件")

    mappings = _build_position_map(text, supports, chunks)
    used_urls: set[str] = set()
    articles = []

    for match in _ARTICLE_PATTERN.finditer(text):
        title = match.group(1).strip()
        summary = match.group(2).strip()

        url = _uri_at_char_pos(match.start(), text, mappings)
        if url is None or url in used_urls:
            url = _uri_by_chunk_title(title, chunks, exclude=used_urls)

        if url:
            used_urls.add(url)
            articles.append({"title": title, "url": url, "summary": summary})
        else:
            logger.warning(f"grounding_supportsにURLが見つかりませんでした: {title}")

    return articles


def _extract_from_chunks(candidate) -> list[dict]:
    """grounding_chunksからURLを抽出する（テキストパース失敗時のフォールバック）。"""
    chunks = []
    seen: set[str] = set()
    if not (candidate.grounding_metadata and candidate.grounding_metadata.grounding_chunks):
        return chunks
    for chunk in candidate.grounding_metadata.grounding_chunks:
        if chunk.web and chunk.web.uri and chunk.web.uri not in seen:
            seen.add(chunk.web.uri)
            real_url = _resolve_url(chunk.web.uri)
            if _is_root_url(real_url):
                logger.warning(f"ルートURLのためスキップ: {chunk.web.uri[:60]}... → {real_url}")
                continue
            logger.debug(f"URL解決: {chunk.web.uri[:60]}... → {real_url}")
            chunks.append({"url": real_url, "title": chunk.web.title or "", "summary": ""})
    return chunks


def _extract_articles(response) -> list[dict]:
    """grounding_supportsで記事を抽出し、失敗時はgrounding_chunksにフォールバック。"""
    candidate = response.candidates[0]

    articles = _parse_articles_with_grounding(response.text, candidate)
    if articles:
        logger.debug(f"grounding_supportsで {len(articles)} 件取得")
        return articles

    logger.warning("grounding_supportsでの取得失敗、grounding_chunksにフォールバック")
    chunks = _extract_from_chunks(candidate)
    logger.debug(f"grounding_chunks から {len(chunks)} 件取得")
    return chunks


def _extract_retry_delay(e: ClientError) -> float:
    """429レスポンスの retryDelay を秒数で返す。取得できなければ 65.0 を返す。"""
    try:
        details_list = e.details.get("error", {}).get("details", [])
        for detail in details_list:
            if "RetryInfo" in detail.get("@type", ""):
                return float(detail["retryDelay"].rstrip("s")) + 5
    except Exception:
        pass
    return 65.0


def _parse_tags(response) -> list[str]:
    """レスポンスからJSONタグ配列をパースする。"""
    text = response.text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        text = match.group(1).strip()
    try:
        tags = json.loads(text)
        if isinstance(tags, list):
            return [str(t) for t in tags if t]
    except json.JSONDecodeError:
        logger.warning(f"タグのJSONパース失敗: {text[:100]}")
    return []


class GeminiClient:
    _EMBED_INTERVAL = 60.0 / 90  # 90 req/min (free tier limit: 100/min)

    def __init__(self, api_key: str):
        self._client = genai.Client(api_key=api_key)
        self._last_embed_time: float = 0.0

    @_retry_server_error
    def _generate(self, prompt: str):
        return self._client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )

    @_retry_server_error
    def _generate_text(self, prompt: str):
        return self._client.models.generate_content(
            model=TAG_MODEL,
            contents=prompt,
        )

    def summarize_article(self, title: str, url: str) -> str:
        """記事タイトルとURLから50字以内の要約を生成する。失敗時は空文字列を返す。"""
        prompt = SUMMARIZE_PROMPT.format(title=title, url=url)
        logger.debug(f"[summarize] model={TAG_MODEL} request prompt:\n{prompt}")
        try:
            response = self._generate_text(prompt)
            logger.debug(f"[summarize] response:\n{response.text}")
            return response.text.strip()
        except Exception as e:
            logger.warning(f"要約生成失敗 ({url}): {e}")
            return ""

    def collect_articles(self, tag_weights: dict[str, float], domains: list[str], favorites: list[dict] | None = None) -> list[dict]:
        if tag_weights:
            topics_str = ", ".join(
                f"{t} ({w:.1f})"
                for t, w in sorted(tag_weights.items(), key=lambda x: x[1], reverse=True)
            )
        else:
            topics_str = "一般技術"
        domains_section = (
            f"\n好みのドメイン（参考）:\n{', '.join(domains)}\n" if domains else ""
        )
        if favorites:
            items_str = "\n".join(
                f"- {f['title']}: {f['excerpt']}"
                for f in favorites if f.get("excerpt")
            )
            favorites_section = f"参考（最近のお気に入り記事・好みのスタイルの参考として）:\n{items_str}\n\n" if items_str else ""
        else:
            favorites_section = ""
        prompt = COLLECT_PROMPT.format(topics=topics_str, domains_section=domains_section, favorites_section=favorites_section)
        logger.debug(f"[collect] model={MODEL} request prompt:\n{prompt}")
        try:
            response = self._generate(prompt)
            logger.debug(f"[collect] response:\n{response.text}")
        except ClientError as e:
            if e.code in (400, 403):
                raise RuntimeError(
                    f"Gemini APIキーが無効です (HTTP {e.code}: {e.status})。"
                    " GEMINI_API_KEY を確認してください。"
                ) from e
            if e.code == 429:
                raise RuntimeError(
                    "Gemini APIのレートリミットに達しました (HTTP 429)。"
                    " しばらく待ってから再実行してください。"
                ) from e
            raise RuntimeError(
                f"Gemini APIエラー (HTTP {e.code}: {e.status})。") from e
        except RetryError as e:
            server_err = e.last_attempt.exception()
            logger.error(f"Gemini ServerError detail: code={server_err.code} status={server_err.status} message={server_err.message}")
            raise RuntimeError(
                f"Gemini APIサーバーエラー (HTTP {server_err.code})。"
                " リトライしましたが回復しませんでした。"
            ) from e

        return _extract_articles(response)

    def embed_text(self, text: str) -> list[float]:
        """テキストを Embedding ベクトルに変換する。"""
        logger.debug(f"[embed] model={EMBED_MODEL} text={text[:80]!r}")
        wait = self._EMBED_INTERVAL - (time.time() - self._last_embed_time)
        if wait > 0:
            time.sleep(wait)
        self._last_embed_time = time.time()
        for attempt in range(3):
            try:
                result = self._client.models.embed_content(
                    model=EMBED_MODEL,
                    contents=text,
                )
                vec = result.embeddings[0].values
                logger.debug(f"[embed] dim={len(vec)}")
                return vec
            except ClientError as e:
                if e.code == 429 and attempt < 2:
                    delay = _extract_retry_delay(e)
                    logger.warning(f"レートリミット (429)、{delay:.0f}秒後にリトライします... ({attempt + 1}/3)")
                    time.sleep(delay)
                    continue
                raise
        return []

    def filter_articles(self, candidates: list[dict], favorites: list[dict] | None = None) -> list[dict]:
        """Embedding上位候補をGemini（Groundingなし）で質フィルタリングする。
        レスポンスの番号から candidates のエントリを返すためURLはLLMに生成させない。
        失敗時は candidates の先頭5件をそのまま返す。
        """
        if not candidates:
            return []

        lines = []
        for i, c in enumerate(candidates, 1):
            lines.append(f"[{i}] タイトル: {c.get('title', '')}")
            if c.get("excerpt"):
                lines.append(f"    要約: {c['excerpt'][:100]}")
        candidates_section = "\n".join(lines)

        if favorites:
            items_str = "\n".join(
                f"- {f['title']}: {f.get('excerpt', '')}"
                for f in favorites if f.get("excerpt")
            )
            favorites_section = f"参考（最近のお気に入り記事）:\n{items_str}\n" if items_str else ""
        else:
            favorites_section = ""

        prompt = FILTER_PROMPT.format(
            favorites_section=favorites_section,
            candidates_section=candidates_section,
        )
        logger.debug(f"[filter] model={TAG_MODEL} request prompt:\n{prompt}")
        try:
            response = self._generate_text(prompt)
            logger.debug(f"[filter] response:\n{response.text}")
        except Exception as e:
            logger.warning(f"フィルタリング失敗、候補先頭5件を返します: {e}")
            return candidates[:5]

        indices = []
        for part in re.split(r"[,\s]+", response.text.strip()):
            part = part.strip()
            if part.isdigit():
                idx = int(part) - 1
                if 0 <= idx < len(candidates) and idx not in indices:
                    indices.append(idx)

        if not indices:
            logger.warning("フィルタリングレスポンス解析失敗、候補先頭5件を返します")
            return candidates[:5]

        return [candidates[i] for i in indices]

    def estimate_tags(self, title: str, url: str, existing_tags: list[str]) -> list[str]:
        prompt = ESTIMATE_TAGS_PROMPT.format(
            existing_tags=json.dumps(existing_tags, ensure_ascii=False),
            title=title,
            url=url,
        )
        logger.debug(f"[estimate_tags] model={TAG_MODEL} request prompt:\n{prompt}")
        for attempt in range(3):
            try:
                response = self._generate_text(prompt)
                logger.debug(f"[estimate_tags] response:\n{response.text}")
                return _parse_tags(response)
            except ClientError as e:
                if e.code == 429 and attempt < 2:
                    delay = _extract_retry_delay(e)
                    logger.warning(f"レートリミット (429)、{delay:.0f}秒後にリトライします... ({attempt + 1}/3)")
                    time.sleep(delay)
                    continue
                logger.warning(f"タグ推定失敗 ({url}): {e}")
                return []
            except RetryError as e:
                logger.warning(f"タグ推定失敗 ({url}): {e}")
                return []
        return []


def create_gemini_client() -> GeminiClient:
    api_key = os.environ["GEMINI_API_KEY"]
    return GeminiClient(api_key)
