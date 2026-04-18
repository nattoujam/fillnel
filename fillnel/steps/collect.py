import logging

from fillnel.services.gemini import GeminiClient
from fillnel.services import profile as profile_svc

logger = logging.getLogger(__name__)

MAX_ARTICLES = 10


def run(gemini: GeminiClient) -> list[dict]:
    profile = profile_svc.load()
    topics = profile_svc.top_tags(profile, n=5)
    logger.info(f"collect: 興味トピック = {topics}")

    articles = gemini.collect_articles(topics)
    logger.info(f"collect: Geminiから{len(articles)}件取得")

    result = articles[:MAX_ARTICLES]
    logger.info(f"collect: {len(result)}件登録予定")
    return result
