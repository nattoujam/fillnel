"""
アプリケーション全体で共有する定数。
チューニングパラメータは.envで上書き可能（デフォルト値付き）。
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _env_int(name: str, default: int) -> int:
    val = os.getenv(name)
    return int(val) if val is not None else default


def _env_float(name: str, default: float) -> float:
    val = os.getenv(name)
    return float(val) if val is not None else default


def _env_str(name: str, default: str) -> str:
    return os.getenv(name, default)


def _env_path(name: str, default: str) -> Path:
    return Path(os.getenv(name, default))


# --- プロファイル・収集パラメータ ---
TOP_FAVORITES = _env_int("TOP_FAVORITES", 5)           # collect に渡すお気に入り記事の最大件数
TOP_TOPICS = _env_int("TOP_TOPICS", 5)                 # プロンプトに渡す興味トピック数
TOP_DOMAINS = _env_int("TOP_DOMAINS", 10)              # プロンプトに渡す好みドメイン数
MAX_ARTICLES = _env_int("MAX_ARTICLES", 10)             # 1バッチで登録する記事の最大件数
WEIGHT_INCREMENT = _env_float("WEIGHT_INCREMENT", 2.0)  # お気に入り記事タグの重み増加量
MAX_FEED_CANDIDATES = _env_int("MAX_FEED_CANDIDATES", 20)  # Embedding上位N件をGeminiフィルタリングに渡す件数

# --- RSS フィード設定 ---
FEEDS_PATH = _env_path("FEEDS_PATH", "config/feeds.yml")

# --- Gemini モデル設定 ---
GEMINI_MODEL = _env_str("GEMINI_MODEL", "gemini-3.1-flash-lite")    # collect/filter 用モデル
GEMINI_TAG_MODEL = _env_str("GEMINI_TAG_MODEL", "gemini-3.1-flash-lite")  # タグ推定・要約用モデル
GEMINI_EMBED_MODEL = _env_str("GEMINI_EMBED_MODEL", "gemini-embedding-001")  # Embedding用モデル

# --- レート制限対策 ---
ENRICH_REQUEST_DELAY = _env_int("ENRICH_REQUEST_DELAY", 5)  # Gemini 15 RPM 制限に対して余裕をもった待機時間（秒）
CHECK_LINKS_REQUEST_DELAY = _env_int("CHECK_LINKS_REQUEST_DELAY", 1)  # リンク確認リクエスト間隔（秒）
