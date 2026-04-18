"""
学習ステップ単体実行エントリポイント。

実行方法:
  poetry run fillnel-learn           # タグなし記事のみ処理
  poetry run fillnel-learn --force   # 全件タグを再推定
"""
import argparse
import logging
import sys

from dotenv import load_dotenv
from rich.logging import RichHandler

from fillnel.services.gemini import create_gemini_client
from fillnel.services.raindrop import create_raindrop_client
from fillnel.steps import FAVORITE_COLLECTION, learn

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
    parser = argparse.ArgumentParser(description="fillnel 学習ステップ")
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
    learn.run(raindrop, gemini, favorite_id, force=args.force)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        logger.error(str(e))
        sys.exit(1)
    except Exception as e:
        logger.error(f"予期せぬエラーが発生しました: {e}")
        sys.exit(1)
