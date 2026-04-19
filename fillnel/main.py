import logging

from dotenv import load_dotenv

from fillnel.cli import run_command, setup_logging
from fillnel.services.gemini import create_gemini_client
from fillnel.services.raindrop import UNSORTED_COLLECTION_ID, create_raindrop_client
from fillnel.steps import FAVORITE_COLLECTION, cleanup, collect, enrich, rebuild_profile, register

setup_logging()
logger = logging.getLogger(__name__)


def _run() -> None:
    load_dotenv()
    raindrop = create_raindrop_client()
    gemini = create_gemini_client()

    favorite_id = raindrop.get_or_create_collection(FAVORITE_COLLECTION)

    logger.info("=== fillnel バッチ開始 ===")
    enrich.run(raindrop, gemini, favorite_id)
    favorites = rebuild_profile.run(raindrop, gemini, favorite_id)
    cleanup.run(raindrop, UNSORTED_COLLECTION_ID)
    articles = collect.run(gemini, favorites)
    register.run(raindrop, articles, UNSORTED_COLLECTION_ID)
    logger.info("=== fillnel バッチ完了 ===")


def main() -> None:
    run_command(_run)


if __name__ == "__main__":
    main()
