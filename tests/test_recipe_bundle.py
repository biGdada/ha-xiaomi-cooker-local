"""Guard the bundled catalogue against Chinese text left in English fields."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "custom_components" / "xiaomi_cooker_local" / "recipes.json"

RECIPE_KEYS = ("name_en", "description_en", "tips_en")
ITEM_KEYS = ("name_en", "content_en", "quantity_en")
COLLECTIONS = ("ingredients", "steps", "foods", "tools")


def _has_chinese(value: object) -> bool:
    return isinstance(value, str) and any("\u4e00" <= c <= "\u9fff" for c in value)


def test_english_fields_are_actually_english() -> None:
    bundle = json.loads(BUNDLE.read_text(encoding="utf-8"))
    offenders: list[str] = []

    def scan(item: dict, keys: tuple[str, ...]) -> None:
        for key in keys:
            value = item.get(key)
            if _has_chinese(value):
                offenders.append(f"recipe {item.get('id', '?')}: {key}={value!r}")

    for recipe in bundle:
        scan(recipe, RECIPE_KEYS)
        for collection in COLLECTIONS:
            for item in recipe.get(collection) or []:
                if not isinstance(item, dict):
                    continue
                scan(item, ITEM_KEYS)
                for child in item.get("ingredients") or []:
                    if isinstance(child, dict):
                        scan(child, ITEM_KEYS)

    assert not offenders, (
        f"{len(offenders)} Chinese values in English fields: {offenders[:5]}"
    )
