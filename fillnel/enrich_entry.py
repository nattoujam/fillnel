"""
エンリッチステップ単体実行エントリポイント。
お気に入りフォルダの記事にexcerpt・タグを付与し、プロファイルを更新する。

実行方法:
  uv run fillnel-enrich           # タグなし記事のみ処理 + プロファイル更新
  uv run fillnel-enrich --force   # 全件タグを再推定 + プロファイル更新
"""
import argparse

from dotenv import load_dotenv

from fillnel.cli import run_command, setup_logging
from fillnel.services.gemini import create_gemini_client
from fillnel.services.raindrop import create_raindrop_client
from fillnel.steps import FAVORITE_COLLECTION, enrich, rebuild_profile

setup_logging()


def main() -> None:
    parser = argparse.ArgumentParser(description="fillnel エンリッチステップ")
    parser.add_argument(
        "--force",
        action="store_true",
        help="タグ付き記事も含め全件タグを再推定する",
    )
    args = parser.parse_args()

    def _run() -> None:
        load_dotenv()
        raindrop = create_raindrop_client()
        gemini = create_gemini_client()
        favorite_id = raindrop.get_or_create_collection(FAVORITE_COLLECTION)
        enrich.run(raindrop, gemini, favorite_id, force=args.force)
        rebuild_profile.run(raindrop, favorite_id)

    run_command(_run)


if __name__ == "__main__":
    main()
