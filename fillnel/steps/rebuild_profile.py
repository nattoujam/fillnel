import hashlib
import logging
from urllib.parse import urlparse

import numpy as np

from fillnel.config import TOP_FAVORITES
from fillnel.services.gemini import GeminiClient
from fillnel.services.raindrop import BookmarkClient
from fillnel.services import profile as profile_svc

logger = logging.getLogger(__name__)


def run(raindrop: BookmarkClient, gemini: GeminiClient, favorite_collection_id: int) -> list[dict]:
    """お気に入り全件からプロファイルを再構築して保存する。
    Embeddingキャッシュを更新し、profile_vector（全件平均）を保存する。
    返り値: excerpt付きのお気に入り記事リスト（filter_articles のプロンプト文脈用）。
    """
    items = raindrop.get_bookmarks(collection_id=favorite_collection_id)
    profile = profile_svc.load()
    profile["tags"] = {}
    profile["domains"] = {}

    cache: dict = profile.get("embedding_cache", {})
    current_urls: set[str] = set()
    vecs: list[list[float]] = []
    favorites: list[dict] = []

    # 1パス目: キャッシュ確認と新規Embedding対象のテキスト収集
    uncached_items: list[tuple[str, str, str]] = []  # (url, content_hash, text)
    uncached_indices: list[int] = []  # vecsリスト内のインデックス

    for idx, item in enumerate(items):
        tags = item.get("tags", [])
        profile_svc.increment(profile, tags)

        domain = urlparse(item.get("link", "")).netloc.removeprefix("www.")
        profile_svc.increment_domains(profile, [domain])

        excerpt = item.get("excerpt", "")
        if excerpt:
            favorites.append({"title": item.get("title", ""), "excerpt": excerpt})

        url = item.get("link", "")
        title = item.get("title", "")
        text = f"{title} {excerpt}".strip()
        if not text or not url:
            continue

        current_urls.add(url)
        content_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
        cached = cache.get(url, {})

        if cached.get("hash") == content_hash:
            vecs.append(cached["vector"])
        else:
            uncached_items.append((url, content_hash, text))
            uncached_indices.append(len(vecs))
            vecs.append(None)  # プレースホルダー

    # 2パス目: 新規Embeddingを一括で取得
    new_count = 0
    if uncached_items:
        texts = [t for _, _, t in uncached_items]
        new_vecs = gemini.embed_texts(texts)
        for i, (url, content_hash, _), vec in zip(uncached_indices, uncached_items, new_vecs):
            vecs[i] = vec
            cache[url] = {"hash": content_hash, "vector": vec}
            new_count += 1

    # お気に入りから外れた記事のキャッシュを削除
    for stale_url in [url for url in cache if url not in current_urls]:
        del cache[stale_url]

    # None（未処理）を除外して平均を計算
    valid_vecs = [v for v in vecs if v is not None]
    if valid_vecs:
        profile["profile_vector"] = np.mean(valid_vecs, axis=0).tolist()
    else:
        profile.pop("profile_vector", None)

    profile["embedding_cache"] = cache
    profile_svc.save(profile)
    logger.info(
        f"rebuild_profile: {len(items)}件からプロファイルを再構築"
        f"（新規Embedding: {new_count}件, キャッシュ: {len(vecs) - new_count}件）"
    )
    return favorites[:TOP_FAVORITES]
