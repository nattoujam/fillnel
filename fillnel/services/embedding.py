import os
import logging
import warnings

# progress bar (tqdm) の抑制は huggingface_hub の import 時に読み込まれる
# 定数で決まるため、import より前に設定する必要がある
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

# HF Hub warning prints (warnings モジュール経由分) を抑制
warnings.filterwarnings("ignore", category=UserWarning, module="huggingface_hub")

import numpy as np
from sentence_transformers import SentenceTransformer

# huggingface_hub / transformers は import 時に自前の StreamHandler を
# 追加し、自身のロガーレベルを WARNING にリセットする。そのため import
# より前に setLevel しても上書きされてしまうので、import 後に設定する。
# (raw ログとして stderr に直接出力されるのを防ぎ、rich handler 経由の
# ログ出力のみに抑える)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("sentence_transformers").setLevel(logging.ERROR)

from fillnel.config import EMBED_EXCERPT_MAX_CHARS

logger = logging.getLogger(__name__)

# ローカル埋め込みモデル（オフライン・無料・高速）
_EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
_embed_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _embed_model
    if _embed_model is None:
        _embed_model = SentenceTransformer(_EMBED_MODEL_NAME)
    return _embed_model


def cosine_similarity(a: list[float], b: list[float]) -> float:
    na = np.array(a, dtype=float)
    nb = np.array(b, dtype=float)
    denom = float(np.linalg.norm(na) * np.linalg.norm(nb))
    if denom == 0.0:
        return 0.0
    return float(np.dot(na, nb) / denom)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """テキストのリストをローカル埋め込みベクトルに変換する。"""
    model = _get_model()
    vecs = model.encode(texts, normalize_embeddings=True)
    return vecs.tolist()


def score_articles(
    articles: list[dict], profile_vector: list[float] | None
) -> list[dict]:
    """articles に "_score" を付与してコサイン類似度降順で返す。
    profile_vector は rebuild_profile ステップで事前計算・キャッシュされたもの。
    None または空の場合はスコアリングをスキップして元リストをそのまま返す。
    """
    if not profile_vector:
        logger.info("profile_vectorがないためスコアリングをスキップ")
        return articles

    texts = [
        f"{a.get('title', '')} {a.get('excerpt', '')[:EMBED_EXCERPT_MAX_CHARS]}".strip()
        for a in articles
    ]
    vecs = embed_texts(texts)

    for article, vec in zip(articles, vecs):
        article["_score"] = cosine_similarity(vec, profile_vector)

    return sorted(articles, key=lambda a: a.get("_score", 0.0), reverse=True)
