import json
import os
from pathlib import Path

PROFILE_PATH = Path(os.environ.get("PROFILE_PATH", "data/profile.json"))
WEIGHT_INCREMENT = 2.0


def load() -> dict:
    if not PROFILE_PATH.exists():
        return {"tags": {}, "domains": {}}
    with open(PROFILE_PATH, encoding="utf-8") as f:
        data = json.load(f)
    # 旧フォーマット（フラット構造）からの自動移行
    if "tags" not in data:
        return {"tags": data, "domains": {}}
    return data


def save(profile: dict) -> None:
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)


def top_tags(profile: dict, n: int = 5) -> list[str]:
    tags = profile.get("tags", {})
    return sorted(tags, key=lambda t: tags[t], reverse=True)[:n]


def top_domains(profile: dict, n: int = 10) -> list[str]:
    domains = profile.get("domains", {})
    return sorted(domains, key=lambda d: domains[d], reverse=True)[:n]


def increment(profile: dict, tags: list[str]) -> dict:
    tag_weights = profile.setdefault("tags", {})
    for tag in tags:
        tag_weights[tag] = tag_weights.get(tag, 0.0) + WEIGHT_INCREMENT
    return profile


def increment_domains(profile: dict, domains: list[str]) -> dict:
    domain_counts = profile.setdefault("domains", {})
    for domain in domains:
        if domain:
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
    return profile
