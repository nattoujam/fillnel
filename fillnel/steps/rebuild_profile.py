import logging
from urllib.parse import urlparse

from fillnel.config import TOP_FAVORITES
from fillnel.services.raindrop import BookmarkClient
from fillnel.services import profile as profile_svc

logger = logging.getLogger(__name__)


def run(raindrop: BookmarkClient, favorite_collection_id: int) -> list[dict]:
    """お気に入り全件からプロファイルを再構築して保存する。
    返り値: excerpt付きのお気に入り記事リスト（collect ステップで使用）。
    """
    items = raindrop.get_bookmarks(collection_id=favorite_collection_id)
    profile = profile_svc.load()
    profile["tags"] = {}
    profile["domains"] = {}

    favorites: list[dict] = []

    for item in items:
        tags = item.get("tags", [])
        profile_svc.increment(profile, tags)

        domain = urlparse(item.get("link", "")).netloc.removeprefix("www.")
        profile_svc.increment_domains(profile, [domain])

        excerpt = item.get("excerpt", "")
        if excerpt:
            favorites.append({"title": item.get("title", ""), "excerpt": excerpt})

    profile_svc.save(profile)
    logger.info(f"rebuild_profile: {len(items)}件からプロファイルを再構築しました")
    return favorites[:TOP_FAVORITES]
