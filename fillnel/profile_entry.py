"""
プロファイル確認コマンド。

実行方法:
  poetry run fillnel-profile
"""
import sys

from dotenv import load_dotenv
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from fillnel.services import profile as profile_svc
from fillnel.steps.collect import TOP_TOPICS

BAR_WIDTH = 28
console = Console()


def _bar(weight: float, max_weight: float) -> str:
    filled = round((weight / max_weight) * BAR_WIDTH)
    return "█" * filled + "░" * (BAR_WIDTH - filled)


def main() -> None:
    load_dotenv()
    profile = profile_svc.load()

    if not profile:
        console.print(Panel(
            "[yellow]プロファイルデータがありません。[/yellow]\n"
            "まだ学習が行われていないか、お気に入りフォルダに記事がありません。",
            title="[bold]fillnel プロファイル[/bold]",
            border_style="yellow",
        ))
        return

    sorted_tags = sorted(profile.items(), key=lambda x: x[1], reverse=True)
    max_weight = sorted_tags[0][1]
    top_n = min(TOP_TOPICS, len(sorted_tags))

    # ── サマリパネル ──────────────────────────────
    summary = Text()
    summary.append(f"{len(sorted_tags)}", style="bold white")
    summary.append(" タグを学習中  /  推薦に使用: 上位 ")
    summary.append(f"{top_n}", style="bold cyan")
    summary.append(" タグ")

    console.print()
    console.print(Panel(summary, title="[bold]fillnel プロファイル[/bold]", border_style="cyan", padding=(0, 2)))

    # ── タグテーブル ──────────────────────────────
    table = Table(
        box=box.ROUNDED,
        border_style="bright_black",
        header_style="bold dim",
        padding=(0, 1),
        show_edge=True,
    )
    table.add_column("#", justify="right", width=3, style="dim")
    table.add_column("タグ", min_width=14)
    table.add_column("重み", justify="right", width=6)
    table.add_column("バー", min_width=BAR_WIDTH + 2)

    for i, (tag, weight) in enumerate(sorted_tags, 1):
        bar = _bar(weight, max_weight)
        is_top = i <= top_n

        if is_top:
            table.add_row(
                str(i),
                f"[bold cyan]{tag}[/bold cyan]",
                f"[bold cyan]{weight:.1f}[/bold cyan]",
                f"[cyan]{bar}[/cyan]",
            )
        else:
            table.add_row(
                str(i),
                f"[dim]{tag}[/dim]",
                f"[dim]{weight:.1f}[/dim]",
                f"[dim]{bar}[/dim]",
            )

        if i == top_n and i < len(sorted_tags):
            table.add_section()

    console.print(table)
    console.print()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        console.print(f"[red]エラー: {e}[/red]")
        sys.exit(1)
