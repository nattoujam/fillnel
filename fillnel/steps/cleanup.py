import logging

from fillnel.services.raindrop import BookmarkClient

logger = logging.getLogger(__name__)


def run(client: BookmarkClient, collection_id: int) -> None:
    logger.info("cleanup: 推薦フォルダの記事を削除します")
    items = client.get_bookmarks(collection_id=collection_id)
    if not items:
        logger.info("cleanup: 削除対象なし")
        return
    ids = [item["_id"] for item in items]
    client.delete_bookmarks(ids)
    logger.info(f"cleanup: {len(ids)}件削除しました")
