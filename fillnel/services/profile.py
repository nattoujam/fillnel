import json
import os
from pathlib import Path

PROFILE_PATH = Path(os.environ.get("PROFILE_PATH", "data/profile.json"))
WEIGHT_INCREMENT = 2.0


def load() -> dict[str, float]:
    if not PROFILE_PATH.exists():
        return {}
    with open(PROFILE_PATH, encoding="utf-8") as f:
        return json.load(f)


def save(profile: dict[str, float]) -> None:
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)


def top_tags(profile: dict[str, float], n: int = 5) -> list[str]:
    return sorted(profile, key=lambda tag: profile[tag], reverse=True)[:n]


def increment(profile: dict[str, float], tags: list[str]) -> dict[str, float]:
    for tag in tags:
        profile[tag] = profile.get(tag, 0.0) + WEIGHT_INCREMENT
    return profile
