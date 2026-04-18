"""
アプリケーション全体で共有する定数。
チューニングパラメータはここで一元管理する。
"""

# --- プロファイル・収集パラメータ ---
TOP_FAVORITES = 5       # collect に渡すお気に入り記事の最大件数
TOP_TOPICS = 5          # プロンプトに渡す興味トピック数
TOP_DOMAINS = 10        # プロンプトに渡す好みドメイン数
MAX_ARTICLES = 10       # 1バッチで登録する記事の最大件数
WEIGHT_INCREMENT = 2.0  # お気に入り記事タグの重み増加量

# --- レート制限対策 ---
ENRICH_REQUEST_DELAY = 5      # Gemini 15 RPM 制限に対して余裕をもった待機時間（秒）
CHECK_LINKS_REQUEST_DELAY = 1  # リンク確認リクエスト間隔（秒）
