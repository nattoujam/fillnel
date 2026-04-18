"""
CLIユーティリティ。ログ設定とエラーハンドリングの共通処理を提供する。
"""
import logging
import sys
from typing import Callable

from rich.logging import RichHandler

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    """ログ設定を初期化する。サードパーティのDEBUGログを抑制する。"""
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


def run_command(fn: Callable[[], None]) -> None:
    """コマンドを実行し、エラー時はログ出力して sys.exit(1) する。"""
    try:
        fn()
    except RuntimeError as e:
        logger.error(str(e))
        sys.exit(1)
    except Exception as e:
        logger.error(f"予期せぬエラーが発生しました: {e}")
        sys.exit(1)
