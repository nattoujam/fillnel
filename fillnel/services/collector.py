import calendar
import logging
import re
import time

import feedparser
import yaml

from fillnel.config import FEEDS_PATH, FEED_MAX_AGE_DAYS

logger = logging.getLogger(__name__)


def load_feeds() -> list[str]:
    if not FEEDS_PATH.exists():
        return []
    with open(FEEDS_PATH) as f:
        data = yaml.safe_load(f) or {}
    return data.get("feeds", [])


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def _is_recent(entry) -> bool:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return True
    return time.time() - calendar.timegm(parsed) <= FEED_MAX_AGE_DAYS * 86400


def fetch_feed(url: str) -> list[dict]:
    logger.debug(f"[feed] fetch: {url}")
    try:
        d = feedparser.parse(url)
        articles = []
        for entry in d.entries:
            link = entry.get("link", "")
            if not link:
                continue
            if not _is_recent(entry):
                continue
            title = entry.get("title", "")
            excerpt = _strip_html(entry.get("summary", ""))
            articles.append({"title": title, "url": link, "excerpt": excerpt})
        logger.debug(f"[feed] {url} → {len(articles)}件")
        return articles
    except Exception as e:
        logger.warning(f"RSS fetch 失敗 ({url}): {e}")
        return []


def collect_from_feeds() -> list[dict]:
    feeds = load_feeds()
    seen: set[str] = set()
    result = []
    for feed_url in feeds:
        articles = fetch_feed(feed_url)
        for article in articles:
            if article["url"] not in seen:
                seen.add(article["url"])
                result.append(article)
    logger.info(f"RSS収集: {len(feeds)}フィードから{len(result)}件取得")
    return result
