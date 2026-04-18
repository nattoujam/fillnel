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
        assert profile_module.load() == {"tags": {}, "domains": {}}

    def test_loads_existing_profile(self, tmp_profile):
        tmp_profile.write_text(json.dumps({"tags": {"AI": 6.0, "TypeScript": 4.0}, "domains": {}}))
        result = profile_module.load()
        assert result == {"tags": {"AI": 6.0, "TypeScript": 4.0}, "domains": {}}

    def test_migrates_flat_format(self, tmp_profile):
        tmp_profile.write_text(json.dumps({"AI": 6.0, "TypeScript": 4.0}))
        result = profile_module.load()
        assert result == {"tags": {"AI": 6.0, "TypeScript": 4.0}, "domains": {}}


class TestSave:
    def test_creates_file(self, tmp_profile):
        profile_module.save({"tags": {"AI": 6.0}, "domains": {}})
        assert tmp_profile.exists()

    def test_saves_and_reloads(self, tmp_profile):
        data = {"tags": {"AI": 6.0, "TypeScript": 4.0}, "domains": {"zenn.dev": 3}}
        profile_module.save(data)
        assert profile_module.load() == data

    def test_creates_parent_directory(self, tmp_path, monkeypatch):
        nested = tmp_path / "nested" / "dir" / "profile.json"
        monkeypatch.setattr(profile_module, "PROFILE_PATH", nested)
        profile_module.save({"tags": {"AI": 1.0}, "domains": {}})
        assert nested.exists()


class TestTopTags:
    def test_returns_sorted_by_weight(self):
        profile = {"tags": {"AI": 6.0, "TypeScript": 4.0, "自己ホスト": 2.0}, "domains": {}}
        assert profile_module.top_tags(profile) == ["AI", "TypeScript", "自己ホスト"]

    def test_limits_to_n(self):
        profile = {"tags": {"A": 5.0, "B": 4.0, "C": 3.0, "D": 2.0, "E": 1.0}, "domains": {}}
        assert profile_module.top_tags(profile, n=3) == ["A", "B", "C"]

    def test_returns_all_when_fewer_than_n(self):
        profile = {"tags": {"AI": 6.0}, "domains": {}}
        assert profile_module.top_tags(profile, n=5) == ["AI"]

    def test_empty_profile(self):
        assert profile_module.top_tags({"tags": {}, "domains": {}}) == []


class TestTopDomains:
    def test_returns_sorted_by_count(self):
        profile = {"tags": {}, "domains": {"zenn.dev": 5, "qiita.com": 3, "github.com": 1}}
        assert profile_module.top_domains(profile) == ["zenn.dev", "qiita.com", "github.com"]

    def test_limits_to_n(self):
        profile = {"tags": {}, "domains": {"a.com": 5, "b.com": 4, "c.com": 3, "d.com": 2}}
        assert profile_module.top_domains(profile, n=2) == ["a.com", "b.com"]

    def test_empty_domains(self):
        assert profile_module.top_domains({"tags": {}, "domains": {}}) == []


class TestIncrement:
    def test_adds_weight_to_existing_tags(self):
        profile = {"tags": {"AI": 4.0}, "domains": {}}
        result = profile_module.increment(profile, ["AI"])
        assert result["tags"]["AI"] == 6.0

    def test_creates_new_tag_with_base_weight(self):
        profile = {"tags": {}, "domains": {}}
        result = profile_module.increment(profile, ["新タグ"])
        assert result["tags"]["新タグ"] == 2.0

    def test_increments_multiple_tags(self):
        profile = {"tags": {"AI": 2.0}, "domains": {}}
        result = profile_module.increment(profile, ["AI", "TypeScript"])
        assert result["tags"]["AI"] == 4.0
        assert result["tags"]["TypeScript"] == 2.0

    def test_mutates_and_returns_same_dict(self):
        profile = {"tags": {}, "domains": {}}
        result = profile_module.increment(profile, ["AI"])
        assert result is profile


class TestIncrementDomains:
    def test_increments_domain_count(self):
        profile = {"tags": {}, "domains": {}}
        result = profile_module.increment_domains(profile, ["zenn.dev"])
        assert result["domains"]["zenn.dev"] == 1

    def test_increments_existing_domain(self):
        profile = {"tags": {}, "domains": {"zenn.dev": 2}}
        result = profile_module.increment_domains(profile, ["zenn.dev"])
        assert result["domains"]["zenn.dev"] == 3

    def test_skips_empty_domain(self):
        profile = {"tags": {}, "domains": {}}
        result = profile_module.increment_domains(profile, [""])
        assert result["domains"] == {}
