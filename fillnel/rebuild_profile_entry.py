"""
プロファイル再構築ステップ単体実行エントリポイント。
Gemini呼び出しなしで、現在のお気に入り全件からプロファイルを再構築する。

実行方法:
  poetry run fillnel-rebuild-profile
"""
from dotenv import load_dotenv

from fillnel.cli import run_command, setup_logging
from fillnel.services.gemini import create_gemini_client
from fillnel.services.raindrop import create_raindrop_client
from fillnel.steps import FAVORITE_COLLECTION, rebuild_profile

setup_logging()


def _run() -> None:
    load_dotenv()
    raindrop = create_raindrop_client()
    gemini = create_gemini_client()
    favorite_id = raindrop.get_or_create_collection(FAVORITE_COLLECTION)
    rebuild_profile.run(raindrop, gemini, favorite_id)


def main() -> None:
    run_command(_run)


if __name__ == "__main__":
    main()
