"""Cooking profile library and model-to-profile-group mapping."""

from __future__ import annotations

import json
import string
from functools import lru_cache
from pathlib import Path
from typing import Any

from .const import KNOWN_MODELS

_PROFILES_FILE = Path(__file__).with_name("profiles.json")

MODEL_GROUPS: dict[str, str] = {
    "chunmi.cooker.press1": "MODEL_PRESSURE",
    "chunmi.cooker.press2": "MODEL_PRESSURE",
    "chunmi.cooker.normal2": "MODEL_NORMAL_GROUP1",
    "chunmi.cooker.normal5": "MODEL_NORMAL_GROUP1",
    "chunmi.cooker.normal1": "MODEL_NORMAL_GROUP2",
    "chunmi.cooker.normal3": "MODEL_NORMAL_GROUP2",
    "chunmi.cooker.normal4": "MODEL_NORMAL_GROUP2",
}


@lru_cache(maxsize=1)
def builtin_groups() -> dict[str, list[dict[str, str]]]:
    """Load the upstream python-miio profile library."""
    return json.loads(_PROFILES_FILE.read_text(encoding="utf-8"))


def group_for_model(model: str | None) -> str | None:
    if not model:
        return None
    if model in MODEL_GROUPS:
        return MODEL_GROUPS[model]
    if model.startswith("chunmi.cooker.press") or model.startswith("chunmi.pre_cooker"):
        return "MODEL_PRESSURE"
    if "normal" in model or "cooker" in model:
        return "MODEL_NORMAL_GROUP1"
    return None


def profiles_for_model(model: str | None) -> list[dict[str, str]]:
    """Return applicable profiles, de-duplicated by profile hex."""
    groups = builtin_groups()
    group = group_for_model(model)
    if group and group in groups:
        selected = [group]
    elif model and model not in KNOWN_MODELS:
        # Unknown model: offer both normal groups so the user can experiment.
        selected = ["MODEL_NORMAL_GROUP1", "MODEL_NORMAL_GROUP2"]
    else:
        selected = ["MODEL_NORMAL_GROUP1", "MODEL_NORMAL_GROUP2"]

    seen: set[str] = set()
    result: list[dict[str, str]] = []
    for name in selected:
        for entry in groups.get(name, []):
            profile = entry["profile"]
            if profile in seen:
                continue
            seen.add(profile)
            result.append(
                {
                    "title": entry["title"],
                    "description": entry.get("description", ""),
                    "profile": profile,
                    "group": name,
                }
            )
    return result


def custom_profiles(raw: Any) -> list[dict[str, str]]:
    """Normalise user supplied profiles from options."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if isinstance(raw, dict):
        raw = [
            {"title": title, "profile": profile}
            for title, profile in raw.items()
        ]
    if not isinstance(raw, list):
        return []

    result: list[dict[str, str]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        profile = str(entry.get("profile", "")).strip()
        if not is_valid_profile(profile):
            continue
        result.append(
            {
                "title": str(entry.get("title") or "Custom profile"),
                "description": str(entry.get("description", "")),
                "profile": profile,
                "group": "CUSTOM",
            }
        )
    return result


def is_valid_profile(profile: str) -> bool:
    profile = profile.strip()
    return (
        len(profile) in (228, 242)
        and all(char in string.hexdigits for char in profile)
    )


def resolve_profile(model: str | None, value: str | None, custom: Any = None) -> str:
    """Resolve a profile title or raw hex string into a hex profile.

    Raises ValueError for unknown titles or malformed hex.
    """
    if not value:
        raise ValueError("No profile given")

    candidate = value.strip()
    if is_valid_profile(candidate):
        return candidate.lower()

    all_profiles = profiles_for_model(model) + custom_profiles(custom)
    for entry in all_profiles:
        if entry["title"].lower() == candidate.lower():
            return entry["profile"].lower()

    raise ValueError(f"Unknown profile: {value}")


def profile_titles(model: str | None, custom: Any = None) -> list[str]:
    return [
        entry["title"]
        for entry in profiles_for_model(model) + custom_profiles(custom)
    ]
