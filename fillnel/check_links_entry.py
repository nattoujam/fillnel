"""
リンク切れ検出バッチ。

実行方法:
  uv run fillnel-check-links
"""
from dotenv import load_dotenv

from fillnel.cli import run_command, setup_logging
from fillnel.services.raindrop import create_raindrop_client
from fillnel.steps import BROKEN_LINK_COLLECTION, check_links

setup_logging()


def _run() -> None:
    load_dotenv()
    raindrop = create_raindrop_client()
    broken_id = raindrop.get_or_create_collection(BROKEN_LINK_COLLECTION)
    check_links.run(raindrop, broken_id)


def main() -> None:
    run_command(_run)


if __name__ == "__main__":
    main()
