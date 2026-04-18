import logging
import os

import requests
from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, RetryError

logger = logging.getLogger(__name__)

MODEL = "gemini-2.5-flash"

COLLECT_PROMPT = """\
以下のトピックに関する最近の記事を5件探してください。

トピック: {topics}

各記事について50字以内の日本語要約を添えてください。
"""


def _resolve_url(url: str) -> str:
    """リダイレクトURLを辿って最終URLを返す。失敗時は元のURLを返す。"""
    try:
        resp = requests.head(url, allow_redirects=True, timeout=5)
        return resp.url
    except Exception:
        return url


def _extract_articles(response) -> list[dict]:
    """grounding_chunksから重複排除した実URLのリストを返す。"""
    candidate = response.candidates[0]

    # grounding_chunksから実URL・タイトルを取得（重複除去）
    chunks = []
    seen = set()
    if candidate.grounding_metadata and candidate.grounding_metadata.grounding_chunks:
        for chunk in candidate.grounding_metadata.grounding_chunks:
            if chunk.web and chunk.web.uri and chunk.web.uri not in seen:
                seen.add(chunk.web.uri)
                real_url = _resolve_url(chunk.web.uri)
                logger.debug(f"URL解決: {chunk.web.uri[:60]}... → {real_url}")
                chunks.append({
                    "url": real_url,
                    "summary": "",
                })

    logger.debug(f"grounding_chunks から {len(chunks)} 件のURLを取得")
    return chunks


class GeminiClient:
    def __init__(self, api_key: str):
        self._client = genai.Client(api_key=api_key)

    @retry(
        retry=retry_if_exception_type(ServerError),
        wait=wait_exponential(multiplier=1, min=5, max=60),
        stop=stop_after_attempt(3),
        before_sleep=lambda rs: logger.warning(
            f"Gemini APIサーバーエラー、リトライします ({rs.attempt_number}/3)... "
            f"code={rs.outcome.exception().code} message={rs.outcome.exception().message}"
        ),
    )
    def _generate(self, prompt: str):
        return self._client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )

    def collect_articles(self, topics: list[str]) -> list[dict]:
        prompt = COLLECT_PROMPT.format(
            topics=", ".join(topics) if topics else "一般技術")
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


def create_gemini_client() -> GeminiClient:
    api_key = os.environ["GEMINI_API_KEY"]
    return GeminiClient(api_key)
