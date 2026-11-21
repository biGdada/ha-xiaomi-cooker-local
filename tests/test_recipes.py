"""Tests for the local recipe catalogue and helper functions."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import custom_components.xiaomi_cooker_local.recipes as recipes_module
from custom_components.xiaomi_cooker_local.recipes import (
    RecipeLibrary,
    crc16_xmodem,
    language_code,
    language_label,
    make_runnable,
    merge_english,
    translate_missing,
)


def _library(*, language: str = "en", original: bool = False) -> RecipeLibrary:
    """Build a library instance without importing Home Assistant."""
    library = object.__new__(RecipeLibrary)
    library.hass = SimpleNamespace(config=SimpleNamespace(language=language))
    library.language_mode = "original" if original else "ha"
    library._recipes = []
    library._by_id = {}
    library._favorites = set()
    library._listeners = set()
    library.last_query = ""
    library.last_search = []
    library.last_recipe = None
    return library


def _recipe() -> dict:
    return {
        "id": 1823,
        "name_zh": "和风温泉蛋",
        "name_en": "Japanese hot spring egg",
        "description_zh": "温泉蛋的描述",
        "description_en": "Onsen egg description",
        "tips_zh": "小贴士",
        "tips_en": "Tips",
        "duration": 25,
        "cover_image": "https://example.com/egg.jpg",
        "ingredients": [
            {
                "name_zh": "鸡蛋",
                "name_en": "egg",
                "quantity_zh": "4--6枚",
                "quantity_en": "4-6 eggs",
            }
        ],
        "steps": [
            {"content_zh": "加水", "content_en": "Add water", "image": ""}
        ],
        "foods": [
            {
                "name_zh": "蛋液",
                "name_en": "Egg mixture",
                "ingredients": [
                    {
                        "name_zh": "酱油",
                        "name_en": "soy sauce",
                        "quantity_zh": "少许",
                        "quantity_en": "a little",
                    }
                ],
            }
        ],
        "tools": [{"name_zh": "量杯", "name_en": "measuring cup", "image": ""}],
        "cookcode": "aa" * 133,
        "runnable_cookcode": "bb" * 133,
    }


def test_language_helpers() -> None:
    assert language_code("en_US") == "en"
    assert language_code("de-DE") == "en"
    assert language_code("zh_Hans") == "zh"
    assert language_label("en") == "English"
    assert language_label("de_DE") == "Deutsch"
    assert language_label("fr-FR") == "Français"
    assert language_label("zh_CN") == "简体中文"


def test_make_runnable_uses_slot_05_and_recomputes_crc() -> None:
    cloud = bytearray(range(133))
    runnable = bytes.fromhex(make_runnable(cloud.hex()))

    assert len(runnable) == 133
    assert runnable[2] == 0x05
    assert runnable[7] & 0x80 == 0
    assert int.from_bytes(runnable[-2:], "big") == crc16_xmodem(runnable[:-2])


def test_merge_english_keeps_bundled_translations() -> None:
    bundled = _recipe()
    refreshed = [
        {
            "id": 1823,
            "name_zh": bundled["name_zh"],
            "name_en": "",
            "description_en": "",
            "tips_en": "",
            "ingredients": [
                {"name_en": "", "quantity_en": ""},
            ],
            "steps": [{"content_en": ""}],
            "foods": [
                {"name_en": "", "ingredients": [{"name_en": "", "quantity_en": ""}]}
            ],
            "tools": [{"name_en": ""}],
        }
    ]

    merge_english(refreshed, [bundled])

    assert refreshed[0]["name_en"] == "Japanese hot spring egg"
    assert refreshed[0]["ingredients"][0]["quantity_en"] == "4-6 eggs"
    assert refreshed[0]["steps"][0]["content_en"] == "Add water"
    assert refreshed[0]["foods"][0]["ingredients"][0]["name_en"] == "soy sauce"
    assert refreshed[0]["tools"][0]["name_en"] == "measuring cup"


def test_refresh_translates_missing_strings_from_cache_without_network() -> None:
    recipe = _recipe()
    for field in ("name_en", "description_en", "tips_en"):
        recipe[field] = ""
    for item in recipe["ingredients"]:
        item["name_en"] = ""
        item["quantity_en"] = ""
    recipe["steps"][0]["content_en"] = ""
    recipe["foods"][0]["name_en"] = ""
    recipe["foods"][0]["ingredients"][0]["name_en"] = ""
    recipe["foods"][0]["ingredients"][0]["quantity_en"] = ""
    recipe["tools"][0]["name_en"] = ""

    cache = {
        "和风温泉蛋": "Japanese hot spring egg",
        "温泉蛋的描述": "Onsen egg description",
        "小贴士": "Tips",
        "鸡蛋": "egg",
        "4--6枚": "4-6 eggs",
        "加水": "Add water",
        "蛋液": "Egg mixture",
        "酱油": "soy sauce",
        "少许": "a little",
        "量杯": "measuring cup",
    }
    translate_missing([recipe], cache)

    assert recipe["name_en"] == "Japanese hot spring egg"
    assert recipe["ingredients"][0]["quantity_en"] == "4-6 eggs"
    assert recipe["steps"][0]["content_en"] == "Add water"
    assert recipe["foods"][0]["ingredients"][0]["name_en"] == "soy sauce"
    assert recipe["tools"][0]["name_en"] == "measuring cup"


def test_translate_missing_surfaces_rate_limit(monkeypatch) -> None:
    recipe = _recipe()
    recipe["name_en"] = ""

    class Response:
        status_code = 429

    monkeypatch.setattr(
        recipes_module.requests, "get", lambda *args, **kwargs: Response()
    )

    stats = translate_missing([recipe], {})

    assert stats["failed"] == 1
    assert "rate-limited" in stats["error"]
    # A failed translation must never write Chinese into an English field.
    assert recipe["name_en"] == ""


def test_poisoned_english_field_is_retranslated(monkeypatch) -> None:
    recipe = _recipe()
    recipe["name_en"] = recipe["name_zh"]

    class Response:
        status_code = 200

        def json(self):
            return [[["Onsen egg", "和风温泉蛋"]]]

    monkeypatch.setattr(
        recipes_module.requests, "get", lambda *args, **kwargs: Response()
    )

    stats = translate_missing([recipe], {})

    assert stats["failed"] == 0
    assert stats["translated"] == 1
    assert recipe["name_en"] == "Onsen egg"


def test_translate_missing_prioritizes_titles_and_ingredients(monkeypatch) -> None:
    recipe = _recipe()
    recipe["name_en"] = ""
    recipe["description_en"] = ""
    recipe["ingredients"][0]["name_en"] = ""
    recipe["ingredients"][0]["quantity_en"] = ""
    recipe["steps"][0]["content_en"] = ""
    recipe["foods"][0]["name_en"] = ""
    recipe["foods"][0]["ingredients"][0]["name_en"] = ""

    translations = {
        "和风温泉蛋": "Japanese hot spring egg",
        "温泉蛋的描述": "Onsen egg description",
        "鸡蛋": "egg",
        "4--6枚": "4-6 eggs",
        "加水": "Add water",
        "蛋液": "Egg mixture",
        "酱油": "soy sauce",
        "少许": "a little",
        "量杯": "measuring cup",
        "小贴士": "Tips",
    }
    events: list[str] = []
    callbacks = 0

    def fake_translate(text: str, cache: dict[str, str]) -> tuple[str, str, str | None]:
        key = text.strip()
        events.append(f"translate:{key}")
        return key, translations.get(key, key), None

    def publish() -> None:
        nonlocal callbacks
        callbacks += 1
        events.append(f"publish:{callbacks}")
        assert recipe["name_en"] == "Japanese hot spring egg"
        assert recipe["ingredients"][0]["name_en"] == "egg"
        assert recipe["steps"][0]["content_en"] == ""

    monkeypatch.setattr(recipes_module, "_translate_one", fake_translate)

    translate_missing(
        [recipe],
        {},
        progress=lambda p, *_: events.append(p),
        on_priority_done=publish,
    )

    assert "translate_priority" in events
    assert "translate_details" in events
    assert (
        events.index("translate_priority")
        < events.index("publish:1")
        < events.index("translate_details")
    )
    assert callbacks == 1
    assert recipe["name_en"] == "Japanese hot spring egg"
    assert recipe["ingredients"][0]["name_en"] == "egg"
    assert recipe["steps"][0]["content_en"] == "Add water"


def test_search_and_detail_follow_ha_language_then_original() -> None:
    recipe = _recipe()
    library = _library()
    library._recipes = [recipe]
    library._by_id = {recipe["id"]: recipe}
    library._favorites = {recipe["id"]}

    results = library.search("温泉蛋")
    assert len(results) == 1
    assert results[0]["name"] == "Japanese hot spring egg"
    assert results[0]["favorite"] is True

    detail = library.detail(recipe)
    assert detail["ingredients"][0]["name"] == "egg"
    assert detail["steps"][0]["content"] == "Add water"
    assert detail["favorite"] is True

    library.language_mode = "original"
    detail_zh = library.detail(library.resolve("Japanese hot spring egg"))
    assert detail_zh["name"] == "和风温泉蛋"
    assert detail_zh["ingredients"][0]["name"] == "鸡蛋"
    assert detail_zh["steps"][0]["content"] == "加水"


def test_search_matches_english_name_and_ingredients() -> None:
    recipe = _recipe()
    library = _library()
    library._recipes = [recipe]
    library._by_id = {recipe["id"]: recipe}

    assert library.search("onsen")[0]["id"] == 1823
    assert library.search("soy sauce")[0]["id"] == 1823
    assert library.search("鸡蛋")[0]["id"] == 1823
    assert library.search("") == [] or library.search("")[0]["id"] == 1823


def test_bundled_catalogue_is_complete_and_runnable() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "xiaomi_cooker_local"
        / "recipes.json"
    )
    recipes = json.loads(path.read_text(encoding="utf-8"))

    assert len(recipes) >= 490
    assert len({recipe["id"] for recipe in recipes}) == len(recipes)
    for recipe in recipes:
        assert recipe["name_zh"]
        assert recipe["name_en"]
        assert len(recipe["cookcode"]) == 266
        runnable = bytes.fromhex(recipe["runnable_cookcode"])
        assert len(runnable) == 133
        assert runnable[2] == 0x05
        assert runnable[7] & 0x80 == 0
        assert int.from_bytes(runnable[-2:], "big") == crc16_xmodem(runnable[:-2])

    onsen = next(recipe for recipe in recipes if recipe["id"] == 1823)
    assert onsen["name_zh"] == "和风温泉蛋"
    assert onsen["ingredients"]


def test_language_selector_labels_use_real_language_name() -> None:
    library = _library(language="de-DE")
    assert library.language_options == [
        "Deutsch",
        "中文 (Original)",
    ]
    assert library.language_label == "Deutsch"

    library = _library(language="zh-CN")
    assert library.language_options == ["简体中文"]
    assert library.language_label == "简体中文"
