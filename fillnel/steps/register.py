import logging

from fillnel.services.raindrop import BookmarkClient

logger = logging.getLogger(__name__)


def run(client: BookmarkClient, articles: list[dict], collection_id: int) -> None:
    logger.info(f"register: {len(articles)}件を登録します")
    for article in articles:
        bookmark = {
            "link": article["url"],
            "excerpt": article.get("summary", ""),
            "collection": {"$id": collection_id},
        }
        if title := article.get("title"):
            bookmark["title"] = title
        client.create_bookmark(bookmark)
    logger.info("register: 完了")
