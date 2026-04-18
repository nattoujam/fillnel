import logging
import time
from urllib.parse import urlparse

from fillnel.services.gemini import GeminiClient
from fillnel.services.raindrop import BookmarkClient
from fillnel.services import profile as profile_svc

logger = logging.getLogger(__name__)

# 15 RPM制限に対して余裕をもって12 RPM以下に抑える（60 / 12 = 5秒）
INTER_REQUEST_DELAY = 5


def run(raindrop: BookmarkClient, gemini: GeminiClient, favorite_collection_id: int, force: bool = False) -> None:
    items = raindrop.get_bookmarks(collection_id=favorite_collection_id)
    if not items:
        logger.info("learn: お気に入りフォルダに記事なし")
        return

    if force:
        logger.info(f"learn: {len(items)}件を処理します（全件再推定モード）")
    else:
        logger.info(f"learn: {len(items)}件を処理します")
    existing_tags = raindrop.get_tags()
    profile = profile_svc.load()

    for item in items:
        tags = item.get("tags", [])
        if not tags or force:
            tags = gemini.estimate_tags(
                title=item.get("title", ""),
                url=item.get("link", ""),
                existing_tags=existing_tags,
            )
            if tags:
                raindrop.update_bookmark(item["_id"], {"tags": tags})
                logger.info(f"learn: タグ付与 {item.get('link', '')} → {tags}")
            time.sleep(INTER_REQUEST_DELAY)

        profile_svc.increment(profile, tags)

        domain = urlparse(item.get("link", "")).netloc.removeprefix("www.")
        profile_svc.increment_domains(profile, [domain])

    profile_svc.save(profile)
    logger.info("learn: プロファイル更新完了")
