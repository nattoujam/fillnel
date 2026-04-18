import logging
import time

from fillnel.services.gemini import GeminiClient
from fillnel.services.raindrop import BookmarkClient

logger = logging.getLogger(__name__)

# 15 RPM制限に対して余裕をもって12 RPM以下に抑える（60 / 12 = 5秒）
INTER_REQUEST_DELAY = 5


def run(raindrop: BookmarkClient, gemini: GeminiClient, favorite_collection_id: int, force: bool = False) -> None:
    """お気に入りフォルダの記事にexcerpt・タグを付与する（Gemini呼び出し）。"""
    items = raindrop.get_bookmarks(collection_id=favorite_collection_id)
    if not items:
        logger.info("enrich: お気に入りフォルダに記事なし")
        return

    if force:
        logger.info(f"enrich: {len(items)}件を処理します（全件再推定モード）")
    else:
        logger.info(f"enrich: {len(items)}件を処理します")

    existing_tags = raindrop.get_tags()

    for item in items:
        title = item.get("title", "")
        url = item.get("link", "")
        patch: dict = {}

        # excerptが空の場合は要約を生成して付与
        excerpt = item.get("excerpt", "")
        if not excerpt:
            excerpt = gemini.summarize_article(title=title, url=url)
            if excerpt:
                patch["excerpt"] = excerpt
            time.sleep(INTER_REQUEST_DELAY)

        # タグが空の場合（またはforceの場合）は推定して付与
        tags = item.get("tags", [])
        if not tags or force:
            tags = gemini.estimate_tags(title=title, url=url, existing_tags=existing_tags)
            if tags:
                patch["tags"] = tags
            time.sleep(INTER_REQUEST_DELAY)

        if patch:
            raindrop.update_bookmark(item["_id"], patch)
            logger.info(f"enrich: 更新 {url} patch={list(patch.keys())}")
