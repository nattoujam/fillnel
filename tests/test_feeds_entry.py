import sys
from unittest.mock import patch

import pytest

from fillnel import feeds_entry


@pytest.fixture(autouse=True)
def feeds_path(tmp_path, monkeypatch):
    path = tmp_path / "feeds.yml"
    monkeypatch.setattr("fillnel.feeds_entry.FEEDS_PATH", path)
    return path


class TestLoad:
    def test_returns_empty_when_missing(self, feeds_path):
        assert feeds_entry._load() == []

    def test_returns_urls(self, feeds_path):
        feeds_path.write_text("feeds:\n  - https://zenn.dev/feed\n")
        assert feeds_entry._load() == ["https://zenn.dev/feed"]


class TestCmdList:
    def test_prints_numbered_list(self, feeds_path, capsys):
        feeds_path.write_text("feeds:\n  - https://a.com\n  - https://b.com\n")
        feeds_entry.cmd_list()
        out = capsys.readouterr().out
        assert "1. https://a.com" in out
        assert "2. https://b.com" in out

    def test_prints_message_when_empty(self, capsys):
        feeds_entry.cmd_list()
        assert "ありません" in capsys.readouterr().out


class TestCmdAdd:
    def test_adds_url(self, feeds_path):
        feeds_entry.cmd_add("https://zenn.dev/feed")
        assert "https://zenn.dev/feed" in feeds_entry._load()

    def test_idempotent_on_duplicate(self, feeds_path):
        feeds_entry.cmd_add("https://zenn.dev/feed")
        feeds_entry.cmd_add("https://zenn.dev/feed")
        assert feeds_entry._load().count("https://zenn.dev/feed") == 1

    def test_prints_list_after_add(self, feeds_path, capsys):
        feeds_entry.cmd_add("https://zenn.dev/feed")
        assert "https://zenn.dev/feed" in capsys.readouterr().out


class TestCmdRemove:
    def test_removes_by_url(self, feeds_path):
        feeds_path.write_text("feeds:\n  - https://a.com\n  - https://b.com\n")
        feeds_entry.cmd_remove("https://a.com")
        assert feeds_entry._load() == ["https://b.com"]

    def test_removes_by_index(self, feeds_path):
        feeds_path.write_text("feeds:\n  - https://a.com\n  - https://b.com\n")
        feeds_entry.cmd_remove("1")
        assert feeds_entry._load() == ["https://b.com"]

    def test_exits_on_unknown_url(self, feeds_path):
        with pytest.raises(SystemExit):
            feeds_entry.cmd_remove("https://unknown.com")

    def test_exits_on_out_of_range_index(self, feeds_path):
        feeds_path.write_text("feeds:\n  - https://a.com\n")
        with pytest.raises(SystemExit):
            feeds_entry.cmd_remove("99")


class TestMain:
    def test_list_command(self, feeds_path, monkeypatch, capsys):
        feeds_path.write_text("feeds:\n  - https://zenn.dev/feed\n")
        monkeypatch.setattr(sys, "argv", ["fillnel-feeds", "list"])
        feeds_entry.main()
        assert "https://zenn.dev/feed" in capsys.readouterr().out

    def test_add_command(self, feeds_path, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["fillnel-feeds", "add", "https://zenn.dev/feed"])
        feeds_entry.main()
        assert "https://zenn.dev/feed" in feeds_entry._load()

    def test_remove_command(self, feeds_path, monkeypatch):
        feeds_path.write_text("feeds:\n  - https://zenn.dev/feed\n")
        monkeypatch.setattr(sys, "argv", ["fillnel-feeds", "remove", "1"])
        feeds_entry.main()
        assert feeds_entry._load() == []

    def test_unknown_command_exits(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["fillnel-feeds", "unknown"])
        with pytest.raises(SystemExit):
            feeds_entry.main()
