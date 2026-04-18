"""
プロファイル再構築ステップ単体実行エントリポイント。
Gemini呼び出しなしで、現在のお気に入り全件からプロファイルを再構築する。

実行方法:
  poetry run fillnel-rebuild-profile
"""
import logging
import sys

from dotenv import load_dotenv
from rich.logging import RichHandler

from fillnel.services.raindrop import create_raindrop_client
from fillnel.steps import FAVORITE_COLLECTION, rebuild_profile

logging.basicConfig(
    level=logging.DEBUG,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, markup=True)],
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def main() -> None:
    load_dotenv()
    raindrop = create_raindrop_client()

    favorite_id = raindrop.get_or_create_collection(FAVORITE_COLLECTION)
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
