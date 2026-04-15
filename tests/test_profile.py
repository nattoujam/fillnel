import json
from pathlib import Path

import pytest

import fillnel.services.profile as profile_module


@pytest.fixture(autouse=True)
def tmp_profile(tmp_path, monkeypatch):
    path = tmp_path / "profile.json"
    monkeypatch.setattr(profile_module, "PROFILE_PATH", path)
    return path


class TestLoad:
    def test_returns_empty_when_file_not_exists(self):
        assert profile_module.load() == {}

    def test_loads_existing_profile(self, tmp_profile):
        tmp_profile.write_text(json.dumps({"AI": 6.0, "TypeScript": 4.0}))
        result = profile_module.load()
        assert result == {"AI": 6.0, "TypeScript": 4.0}


class TestSave:
    def test_creates_file(self, tmp_profile):
        profile_module.save({"AI": 6.0})
        assert tmp_profile.exists()

    def test_saves_and_reloads(self, tmp_profile):
        data = {"AI": 6.0, "TypeScript": 4.0}
        profile_module.save(data)
        assert profile_module.load() == data

    def test_creates_parent_directory(self, tmp_path, monkeypatch):
        nested = tmp_path / "nested" / "dir" / "profile.json"
        monkeypatch.setattr(profile_module, "PROFILE_PATH", nested)
        profile_module.save({"AI": 1.0})
        assert nested.exists()


class TestTopTags:
    def test_returns_sorted_by_weight(self):
        profile = {"AI": 6.0, "TypeScript": 4.0, "自己ホスト": 2.0}
        assert profile_module.top_tags(profile) == ["AI", "TypeScript", "自己ホスト"]

    def test_limits_to_n(self):
        profile = {"A": 5.0, "B": 4.0, "C": 3.0, "D": 2.0, "E": 1.0}
        assert profile_module.top_tags(profile, n=3) == ["A", "B", "C"]

    def test_returns_all_when_fewer_than_n(self):
        profile = {"AI": 6.0}
        assert profile_module.top_tags(profile, n=5) == ["AI"]

    def test_empty_profile(self):
        assert profile_module.top_tags({}) == []


class TestIncrement:
    def test_adds_weight_to_existing_tags(self):
        profile = {"AI": 4.0}
        result = profile_module.increment(profile, ["AI"])
        assert result["AI"] == 6.0

    def test_creates_new_tag_with_base_weight(self):
        profile = {}
        result = profile_module.increment(profile, ["新タグ"])
        assert result["新タグ"] == 2.0

    def test_increments_multiple_tags(self):
        profile = {"AI": 2.0}
        result = profile_module.increment(profile, ["AI", "TypeScript"])
        assert result["AI"] == 4.0
        assert result["TypeScript"] == 2.0

    def test_mutates_and_returns_same_dict(self):
        profile = {}
        result = profile_module.increment(profile, ["AI"])
        assert result is profile
