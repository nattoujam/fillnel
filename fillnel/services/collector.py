import logging
import re

import feedparser
import yaml

from fillnel.config import FEEDS_PATH

logger = logging.getLogger(__name__)


def load_feeds() -> list[str]:
    if not FEEDS_PATH.exists():
        return []
    with open(FEEDS_PATH) as f:
        data = yaml.safe_load(f) or {}
    return data.get("feeds", [])


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def fetch_feed(url: str) -> list[dict]:
    logger.debug(f"[feed] fetch: {url}")
    try:
        d = feedparser.parse(url)
        articles = []
        for entry in d.entries:
            link = entry.get("link", "")
            if not link:
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
