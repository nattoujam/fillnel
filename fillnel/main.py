import logging
import sys

from dotenv import load_dotenv
from rich.logging import RichHandler

from fillnel.services.gemini import create_gemini_client
from fillnel.services.raindrop import UNSORTED_COLLECTION_ID, create_raindrop_client
from fillnel.steps import cleanup, collect, register

logging.basicConfig(
    level=logging.DEBUG,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, markup=True)],
)
# サードパーティの詳細ログを抑制
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("google").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def main() -> None:
    load_dotenv()
    raindrop = create_raindrop_client()
    gemini = create_gemini_client()

    logger.info("=== fillnel バッチ開始 ===")
    cleanup.run(raindrop, UNSORTED_COLLECTION_ID)
    articles = collect.run(gemini)
    register.run(raindrop, articles, UNSORTED_COLLECTION_ID)
    logger.info("=== fillnel バッチ完了 ===")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        logger.error(str(e))
        sys.exit(1)
    except Exception as e:
        logger.error(f"予期せぬエラーが発生しました: {e}")
        sys.exit(1)
