import logging

import numpy as np

logger = logging.getLogger(__name__)

EMBED_MODEL = "gemini-embedding-001"


def cosine_similarity(a: list[float], b: list[float]) -> float:
    na = np.array(a, dtype=float)
    nb = np.array(b, dtype=float)
    denom = float(np.linalg.norm(na) * np.linalg.norm(nb))
    if denom == 0.0:
        return 0.0
    return float(np.dot(na, nb) / denom)


def score_articles(articles: list[dict], profile_vector: list[float] | None, client) -> list[dict]:
    """articles に "_score" を付与してコサイン類似度降順で返す。
    client は embed_text(text: str) -> list[float] を持つ任意のオブジェクト。
    profile_vector は rebuild_profile ステップで事前計算・キャッシュされたもの。
    None または空の場合はスコアリングをスキップして元リストをそのまま返す。
    """
    if not profile_vector:
        logger.info("profile_vectorがないためスコアリングをスキップ")
        return articles

    for article in articles:
        text = f"{article.get('title', '')} {article.get('excerpt', '')}".strip()
        vec = client.embed_text(text)
        article["_score"] = cosine_similarity(vec, profile_vector)

    return sorted(articles, key=lambda a: a.get("_score", 0.0), reverse=True)
