import logging
import time

import requests

from fillnel.config import CHECK_LINKS_REQUEST_DELAY
from fillnel.services.raindrop import BookmarkClient, UNSORTED_COLLECTION_ID

logger = logging.getLogger(__name__)

BROKEN_STATUS_CODES = {404, 410}
REQUEST_TIMEOUT = 10


def _check_url(url: str) -> tuple[bool, str]:
    """URLの生死を確認する。(is_broken, reason) を返す。

    - 404 / 410 → リンク切れと判定
    - タイムアウト / 接続エラー → 一時障害の可能性があるためスキップ（is_broken=False）
    """
    headers = {"User-Agent": "Mozilla/5.0 (compatible; fillnel-link-checker)"}
    try:
        resp = requests.head(url, allow_redirects=True, timeout=REQUEST_TIMEOUT, headers=headers)
        if resp.status_code == 405:
            # HEAD を受け付けないサーバーは GET にフォールバック
            resp = requests.get(url, allow_redirects=True, timeout=REQUEST_TIMEOUT, stream=True, headers=headers)
        if resp.status_code in BROKEN_STATUS_CODES:
            return True, f"HTTP {resp.status_code}"
        return False, ""
    except requests.RequestException as e:
        logger.warning(f"check_links: URL確認エラー（スキップ）: {url[:80]} - {e}")
        return False, ""


def run(raindrop: BookmarkClient, broken_collection_id: int) -> None:
    items = raindrop.get_bookmarks()
    skip_ids = {UNSORTED_COLLECTION_ID, broken_collection_id}
    targets = [
        item for item in items
        if item.get("collection", {}).get("$id") not in skip_ids
    ]

    if not targets:
        logger.info("check_links: チェック対象の記事なし")
        return

    logger.info(f"check_links: {len(targets)}件をチェックします")
    broken_count = 0

    for item in targets:
        url = item.get("link", "")
        if not url:
            continue

        is_broken, reason = _check_url(url)
        if is_broken:
            raindrop.update_bookmark(item["_id"], {"collection": {"$id": broken_collection_id}})
            logger.info(f"check_links: リンク切れ [{reason}] {url}")
            broken_count += 1

        time.sleep(CHECK_LINKS_REQUEST_DELAY)

    logger.info(f"check_links: 完了 — {broken_count}件のリンク切れを検出")
