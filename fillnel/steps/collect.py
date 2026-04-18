import logging

from fillnel.services.gemini import GeminiClient
from fillnel.services import profile as profile_svc

logger = logging.getLogger(__name__)

MAX_ARTICLES = 10
TOP_TOPICS = 5
TOP_DOMAINS = 10


def run(gemini: GeminiClient, favorites: list[dict] | None = None) -> list[dict]:
    profile = profile_svc.load()
    top_tags = profile_svc.top_tags(profile, n=TOP_TOPICS)
    all_weights = profile.get("tags", {})
    tag_weights = {t: all_weights[t] for t in top_tags if t in all_weights}
    domains = profile_svc.top_domains(profile, n=TOP_DOMAINS)
    logger.info(f"collect: 興味トピック = {top_tags}")

    articles = gemini.collect_articles(tag_weights, domains, favorites)
    logger.info(f"collect: Geminiから{len(articles)}件取得")

    result = articles[:MAX_ARTICLES]
    logger.info(f"collect: {len(result)}件登録予定")
    return result
