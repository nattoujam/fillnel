"""
エンリッチステップ単体実行エントリポイント。
お気に入りフォルダの記事にexcerpt・タグを付与し、プロファイルを更新する。

実行方法:
  poetry run fillnel-enrich           # タグなし記事のみ処理 + プロファイル更新
  poetry run fillnel-enrich --force   # 全件タグを再推定 + プロファイル更新
"""
import argparse
import logging
import sys

from dotenv import load_dotenv
from rich.logging import RichHandler

from fillnel.services.gemini import create_gemini_client
from fillnel.services.raindrop import create_raindrop_client
from fillnel.steps import FAVORITE_COLLECTION, enrich, rebuild_profile

logging.basicConfig(
    level=logging.DEBUG,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, markup=True)],
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("google").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="fillnel エンリッチステップ")
    parser.add_argument(
        "--force",
        action="store_true",
        help="タグ付き記事も含め全件タグを再推定する",
    )
    args = parser.parse_args()

    load_dotenv()
    raindrop = create_raindrop_client()
    gemini = create_gemini_client()

    favorite_id = raindrop.get_or_create_collection(FAVORITE_COLLECTION)
    enrich.run(raindrop, gemini, favorite_id, force=args.force)
    rebuild_profile.run(raindrop, favorite_id)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        logger.error(str(e))
        sys.exit(1)
    except Exception as e:
        logger.error(f"予期せぬエラーが発生しました: {e}")
        sys.exit(1)
