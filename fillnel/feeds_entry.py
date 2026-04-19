import sys

import yaml

from fillnel.config import FEEDS_PATH


def _load() -> list[str]:
    if not FEEDS_PATH.exists():
        return []
    with open(FEEDS_PATH) as f:
        data = yaml.safe_load(f) or {}
    return data.get("feeds", [])


def _save(feeds: list[str]) -> None:
    FEEDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(FEEDS_PATH, "w") as f:
        yaml.dump({"feeds": feeds}, f, allow_unicode=True, default_flow_style=False)


def _print_list(feeds: list[str]) -> None:
    if not feeds:
        print("登録されているフィードはありません")
        return
    for i, url in enumerate(feeds, 1):
        print(f"{i}. {url}")


def cmd_list() -> None:
    _print_list(_load())


def cmd_add(url: str) -> None:
    feeds = _load()
    if url not in feeds:
        feeds.append(url)
        _save(feeds)
    _print_list(feeds)


def cmd_remove(target: str) -> None:
    feeds = _load()
    try:
        idx = int(target) - 1
        if idx < 0 or idx >= len(feeds):
            print(f"エラー: インデックス {target} は存在しません", file=sys.stderr)
            sys.exit(1)
        feeds.pop(idx)
    except ValueError:
        if target not in feeds:
            print(f"エラー: {target} は登録されていません", file=sys.stderr)
            sys.exit(1)
        feeds.remove(target)
    _save(feeds)
    _print_list(feeds)


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] == "list":
        cmd_list()
    elif args[0] == "add":
        if len(args) < 2:
            print("使い方: fillnel-feeds add <url>", file=sys.stderr)
            sys.exit(1)
        cmd_add(args[1])
    elif args[0] == "remove":
        if len(args) < 2:
            print("使い方: fillnel-feeds remove <url|index>", file=sys.stderr)
            sys.exit(1)
        cmd_remove(args[1])
    else:
        print("使い方: fillnel-feeds [list|add <url>|remove <url|index>]", file=sys.stderr)
        sys.exit(1)
