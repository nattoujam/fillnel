import logging

from fillnel.config import MAX_ARTICLES, MAX_FEED_CANDIDATES
from fillnel.services import profile as profile_svc
from fillnel.services.collector import collect_from_feeds
from fillnel.services.embedding import score_articles
from fillnel.services.gemini import GeminiClient

logger = logging.getLogger(__name__)


def run(gemini: GeminiClient, favorites: list[dict] | None = None) -> list[dict]:
    candidates = collect_from_feeds()
    logger.info(f"collect: RSSから{len(candidates)}件収集")

    profile = profile_svc.load()
    profile_vector = profile.get("profile_vector")

    scored = score_articles(candidates, profile_vector)
    top = scored[:MAX_FEED_CANDIDATES]
    logger.info(f"collect: Embedding上位{len(top)}件をフィルタリングに渡す")

    articles = gemini.filter_articles(top, favorites)
    logger.info(f"collect: Geminiフィルタリング後{len(articles)}件")

    result = articles[:MAX_ARTICLES]
    logger.info(f"collect: {len(result)}件登録予定")
    return result
