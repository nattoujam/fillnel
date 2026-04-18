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

MODEL = "gemini-2.5-flash"
TAG_MODEL = "gemini-3.1-flash-lite-preview"

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

各記事を以下の形式で出力してください：

タイトル: <記事タイトル>
URL: <記事の正確なURL>
要約: <50字以内の日本語要約>
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
    r"URL[:：]\s*(https?://[^\s\n]+)\n"
    r"要約[:：]\s*(.+)"
)


def _is_root_url(url: str) -> bool:
    """ドメインのトップページ（記事URLでない）かどうかを判定する。"""
    parsed = urlparse(url)
    return parsed.path in ("", "/") and not parsed.query


def _grounding_domains(candidate) -> set[str]:
    """grounding_chunksのリダイレクトURLを解決してドメインセットを返す。"""
    domains: set[str] = set()
    if not (candidate.grounding_metadata and candidate.grounding_metadata.grounding_chunks):
        return domains
    for chunk in candidate.grounding_metadata.grounding_chunks:
        if chunk.web and chunk.web.uri:
            resolved = _resolve_url(chunk.web.uri)
            domain = urlparse(resolved).netloc.removeprefix("www.")
            if domain:
                domains.add(domain)
    return domains


def _parse_articles_from_text(text: str, allowed_domains: set[str]) -> list[dict]:
    """レスポンステキストから構造化記事データをパースし、ドメイン検証する。"""
    articles = []
    for title, url, summary in _ARTICLE_PATTERN.findall(text):
        url = url.rstrip(".,)」）")
        domain = urlparse(url).netloc.removeprefix("www.")
        if allowed_domains and domain not in allowed_domains:
            logger.warning(f"グラウンディング外URLをスキップ: {url} (domain={domain})")
            continue
        articles.append({"url": url, "title": title.strip(), "summary": summary.strip()})
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
            chunks.append({"url": real_url, "summary": ""})
    return chunks


def _extract_articles(response) -> list[dict]:
    """レスポンステキストをパース（優先）し、失敗時は grounding_chunks にフォールバック。"""
    candidate = response.candidates[0]
    domains = _grounding_domains(candidate)
    logger.debug(f"grounding domains: {domains}")

    articles = _parse_articles_from_text(response.text, domains)
    if articles:
        logger.debug(f"テキストパースで {len(articles)} 件取得")
        return articles

    logger.warning("テキストパース失敗、grounding_chunksにフォールバック")
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
    def __init__(self, api_key: str):
        self._client = genai.Client(api_key=api_key)

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

    def collect_articles(self, tag_weights: dict[str, float], domains: list[str]) -> list[dict]:
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
        prompt = COLLECT_PROMPT.format(topics=topics_str, domains_section=domains_section)
        logger.debug(f"Gemini request prompt:\n{prompt}")
        try:
            response = self._generate(prompt)
            logger.debug(f"Gemini response:\n{response.text}")
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

    def estimate_tags(self, title: str, url: str, existing_tags: list[str]) -> list[str]:
        prompt = ESTIMATE_TAGS_PROMPT.format(
            existing_tags=json.dumps(existing_tags, ensure_ascii=False),
            title=title,
            url=url,
        )
        logger.debug(f"タグ推定 prompt:\n{prompt}")
        for attempt in range(3):
            try:
                response = self._generate_text(prompt)
                logger.debug(f"タグ推定 response:\n{response.text}")
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
