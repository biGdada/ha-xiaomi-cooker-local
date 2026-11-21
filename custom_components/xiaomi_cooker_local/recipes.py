"""Recipe library for chunmi.cooker.normalcd1.

The catalogue is shipped as ``recipes.json`` and can be refreshed from the
public Joyami API. Refreshing is best-effort: if the API is unavailable the
bundled catalogue stays in place. All network work happens off the event loop.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, urlencode

import requests

if TYPE_CHECKING:  # pragma: no cover - imported only for type checking
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.storage import Store

from .const import (
    CONF_RECIPE_SOURCE,
    DEFAULT_RECIPE_LANGUAGE,
    DEFAULT_RECIPE_SOURCE,
    DOMAIN,
    RECIPE_LANGUAGE_ORIGINAL,
    RECIPE_SOURCE_API,
    RECIPE_SOURCE_CACHE,
)

_LOGGER = logging.getLogger(__name__)

BUNDLED_RECIPES = Path(__file__).with_name("recipes.json")
MANIFEST = Path(__file__).with_name("manifest.json")
CACHE_STORE_VERSION = 1
FAVORITES_STORE_VERSION = 1
TRANSLATION_STORE_VERSION = 1


def _installed_version() -> str:
    """Return the installed integration version from its manifest."""
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8")).get("version", "")
    except (OSError, ValueError):  # pragma: no cover - defensive
        return ""

_JOYAMI_APP_ID = "202007190935014"
_JOYAMI_BASE = "https://gateway.joyami.com"
_JOYAMI_MODEL = "chunmi.cooker.normalcd1"
_JOYAMI_SEARCH_PATH = "/microwaveoven/index/search"
_JOYAMI_DETAIL_PATH = "/microwaveoven/index/getRecipeDetailById"
_TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"

# Native names for languages Home Assistant commonly uses. The first label on
# the language selector uses this name so it never says "HA language".
LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "zh": "中文",
    "zh-cn": "简体中文",
    "zh-hans": "简体中文",
    "zh-hant": "繁體中文",
    "zh-tw": "繁體中文",
    "de": "Deutsch",
    "fr": "Français",
    "es": "Español",
    "it": "Italiano",
    "pt": "Português",
    "pt-br": "Português (Brasil)",
    "nl": "Nederlands",
    "ru": "Русский",
    "uk": "Українська",
    "ja": "日本語",
    "ko": "한국어",
    "pl": "Polski",
    "sv": "Svenska",
    "da": "Dansk",
    "no": "Norsk",
    "nb": "Norsk bokmål",
    "fi": "Suomi",
    "cs": "Čeština",
    "sk": "Slovenčina",
    "hu": "Magyar",
    "ro": "Română",
    "el": "Ελληνικά",
    "tr": "Türkçe",
    "he": "עברית",
    "ar": "العربية",
    "hi": "हिन्दी",
    "th": "ไทย",
    "vi": "Tiếng Việt",
    "id": "Bahasa Indonesia",
}


def language_code(ha_language: str | None) -> str:
    """Map a Home Assistant language tag to a bundled language code."""
    code = (ha_language or "en").lower().replace("_", "-")
    return "zh" if code.startswith("zh") else "en"


def language_label(ha_language: str | None) -> str:
    """Return the native name of HA's language, e.g. English or Deutsch."""
    code = (ha_language or "en").lower().replace("_", "-")
    if code in LANGUAGE_NAMES:
        return LANGUAGE_NAMES[code]
    base = code.split("-", 1)[0]
    return LANGUAGE_NAMES.get(base, ha_language or "English")


def crc16_xmodem(data: bytes) -> int:
    """CRC-16/XMODEM used by CMCookProfile.toHexData()."""
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def make_runnable(cookcode: str) -> str:
    """Rewrite a cloud cookcode for local ``set_start`` (slot 05)."""
    data = bytearray(bytes.fromhex(cookcode))
    if len(data) != 133:
        raise ValueError(f"Unexpected cookcode length: {len(data)} bytes")
    data[2] = 0x05
    data[7] &= 0x7F
    data[-2:] = crc16_xmodem(data[:-2]).to_bytes(2, "big")
    return data.hex()


def _signed_headers(method: str, path: str) -> dict[str, str]:
    timestamp = str(int(time.time() * 1000))
    minute = int(timestamp) // 60000
    nonce = base64.urlsafe_b64encode(
        os.urandom(8) + minute.to_bytes(4, "big")
    ).decode()
    payload = f"{_JOYAMI_APP_ID}&{timestamp}&{nonce}&{method}&{path}"
    signature = base64.urlsafe_b64encode(
        hashlib.sha256(payload.encode()).digest()
    ).decode()
    return {
        "appid": _JOYAMI_APP_ID,
        "version": f"{_JOYAMI_MODEL}: 9",
        "timestamp": timestamp,
        "nonce": nonce,
        "vid": "1",
        "signature": signature,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _api_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    url = _JOYAMI_BASE + path + "?" + urlencode(params)
    response = requests.get(url, headers=_signed_headers("GET", path), timeout=45)
    response.raise_for_status()
    return response.json()


def _api_detail(item: dict[str, Any]) -> dict[str, Any] | None:
    try:
        result = _api_get(
            _JOYAMI_DETAIL_PATH,
            {
                "recipeId": item["id"],
                "deviceId": "1",
                "model": _JOYAMI_MODEL,
                "menuType": "1",
                "language": "zh_CN",
            },
        ).get("result") or {}
    except Exception as err:  # pragma: no cover - network dependent
        _LOGGER.debug("Could not fetch recipe %s: %s", item.get("id"), err)
        return None
    script = next(
        (
            model.get("cookScript")
            for model in result.get("cookModels") or []
            if model.get("model") == _JOYAMI_MODEL
            and len(model.get("cookScript") or "") == 266
        ),
        None,
    )
    if not script:
        return None
    try:
        runnable = make_runnable(script)
    except ValueError:  # pragma: no cover - defensive
        return None
    return {
        "id": item["id"],
        "name_zh": result.get("name") or item.get("name") or "",
        "name_en": "",
        "description_zh": result.get("description") or "",
        "description_en": "",
        "tips_zh": result.get("tips") or "",
        "tips_en": "",
        "duration": result.get("duration") or item.get("duration"),
        "default_keep_warm": result.get("defaultKeepWarmDuration"),
        "min_keep_warm": result.get("minKeepWarmDuration"),
        "max_keep_warm": result.get("maxKeepWarmDuration"),
        "cover_image": result.get("coverImg") or item.get("coverImg") or "",
        "ingredients": [
            {
                "name_zh": entry.get("name") or "",
                "name_en": "",
                "quantity_zh": entry.get("quantity") or "",
                "quantity_en": "",
            }
            for entry in result.get("ingredients") or []
        ],
        "steps": [
            {
                "content_zh": entry.get("content") or "",
                "content_en": "",
                "image": entry.get("coverImg") or "",
            }
            for entry in result.get("steps") or []
        ],
        "foods": [
            {
                "name_zh": entry.get("foodName") or "",
                "name_en": "",
                "ingredients": [
                    {
                        "name_zh": sub.get("name") or "",
                        "name_en": "",
                        "quantity_zh": sub.get("quantity") or "",
                        "quantity_en": "",
                    }
                    for sub in entry.get("ingredients") or []
                ],
            }
            for entry in result.get("foods") or []
        ],
        "tools": [
            {
                "name_zh": entry.get("toolName") or "",
                "name_en": "",
                "image": entry.get("toolImg") or "",
            }
            for entry in result.get("recipeTools") or []
        ],
        "cookcode": script,
        "runnable_cookcode": runnable,
    }


def _pick(recipe: dict[str, Any], zh_key: str, en_key: str, language: str) -> Any:
    zh = recipe.get(zh_key)
    en = recipe.get(en_key)
    if language == "zh":
        return zh or en or ""
    # Home Assistant language not bundled -> English, then original Chinese.
    return en or zh or ""


def _has_chinese(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _translate_one(
    text: str, cache: dict[str, str]
) -> tuple[str, str, str | None]:
    """Translate one Chinese string, reporting throttling/failure to the UI."""
    key = text.strip()
    if not key:
        return "", "", None
    if not _has_chinese(key):
        return key, key, None
    cached = cache.get(key)
    # A cache entry equal to the source is poisoned from an earlier failed
    # attempt; retry it instead of writing Chinese into an English field.
    if cached is not None and cached != key:
        return key, cached, None
    url = (
        _TRANSLATE_URL
        + "?client=gtx&sl=zh-CN&tl=en&dt=t&q="
        + quote(text)
    )
    try:
        response = requests.get(url, timeout=20)
        if response.status_code != 200:
            error = "Translation service unavailable"
            if response.status_code == 429:
                error = "Translation service is rate-limited (HTTP 429)"
            return key, "", error
        payload = response.json()
        result = "".join(
            part[0] for part in (payload[0] or []) if part and part[0]
        ).strip()
    except Exception as err:  # pragma: no cover - network dependent
        _LOGGER.debug("Recipe translation failed for %s: %s", key[:40], err)
        return key, "", "Translation service unavailable"
    if not result or result == key:
        return key, "", "Translation service returned no text"
    return key, result, None


def _english_missing(item: dict[str, Any], zh_key: str) -> bool:
    """Treat an English field copied from Chinese as missing."""
    en = item.get(zh_key[:-3] + "_en")
    zh = item.get(zh_key)
    return not en or (
        isinstance(en, str)
        and isinstance(zh, str)
        and en.strip() == zh.strip()
    )


def _collect_translation_keys(
    item: dict[str, Any], found: set[str]
) -> None:
    for key, value in item.items():
        if isinstance(value, str) and key.endswith("_zh"):
            if _english_missing(item, key) and _has_chinese(value):
                found.add(value.strip())
        elif isinstance(value, list):
            for child in value:
                if isinstance(child, dict):
                    _collect_translation_keys(child, found)


def _apply_translations(item: dict[str, Any], cache: dict[str, str]) -> None:
    for key, value in list(item.items()):
        if isinstance(value, str) and key.endswith("_zh"):
            text = value.strip()
            translation = cache.get(text, "")
            if _english_missing(item, key) and translation and translation != text:
                item[key[:-3] + "_en"] = translation
        elif isinstance(value, list):
            for child in value:
                if isinstance(child, dict):
                    _apply_translations(child, cache)


_PRIORITY_ITEM_KEYS = ("name_zh", "quantity_zh")


def _collect_priority_keys(
    recipes: list[dict[str, Any]], found: set[str]
) -> None:
    """Collect recipe titles and ingredient strings for prioritized translation."""

    def add(item: dict[str, Any], key: str) -> None:
        value = item.get(key)
        if (
            isinstance(value, str)
            and _english_missing(item, key)
            and _has_chinese(value)
        ):
            found.add(value.strip())

    for recipe in recipes:
        add(recipe, "name_zh")
        for ingredient in recipe.get("ingredients") or []:
            if isinstance(ingredient, dict):
                for key in _PRIORITY_ITEM_KEYS:
                    add(ingredient, key)
        for food in recipe.get("foods") or []:
            if not isinstance(food, dict):
                continue
            add(food, "name_zh")
            for ingredient in food.get("ingredients") or []:
                if isinstance(ingredient, dict):
                    for key in _PRIORITY_ITEM_KEYS:
                        add(ingredient, key)


def _pending_translation_keys(keys: set[str], cache: dict[str, str]) -> list[str]:
    return sorted(key for key in keys if key and key not in cache)


def translate_missing(
    recipes: list[dict[str, Any]],
    cache: dict[str, str],
    progress: Callable[[str, int, int], None] | None = None,
    on_priority_done: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Fill missing English fields, translating titles and ingredients first."""
    from concurrent.futures import ThreadPoolExecutor

    # Apply anything already cached so search can use it immediately.
    for recipe in recipes:
        _apply_translations(recipe, cache)

    all_keys: set[str] = set()
    for recipe in recipes:
        _collect_translation_keys(recipe, all_keys)
    priority_keys: set[str] = set()
    _collect_priority_keys(recipes, priority_keys)
    priority_keys &= all_keys

    priority_pending = _pending_translation_keys(priority_keys, cache)
    other_pending = _pending_translation_keys(all_keys - priority_keys, cache)
    total = len(priority_pending) + len(other_pending)
    if not total:
        if progress:
            progress("translate", 0, 0)
        return {"failed": 0, "error": None, "translated": 0}

    snapshot = dict(cache)
    failures = 0
    translated = 0
    first_error: str | None = None
    done = 0

    def run(keys: list[str], phase: str) -> None:
        nonlocal failures, translated, first_error, done
        if not keys:
            return
        with ThreadPoolExecutor(max_workers=8) as pool:
            for index, (key, translation, error) in enumerate(
                pool.map(lambda text: _translate_one(text, snapshot), keys), 1
            ):
                cache[key] = translation
                if translation and translation != key:
                    translated += 1
                if error:
                    failures += 1
                    first_error = first_error or error
                done += 1
                if progress and (index % 25 == 0 or index == len(keys)):
                    progress(phase, done, total)
        for recipe in recipes:
            _apply_translations(recipe, cache)

    run(priority_pending, "translate_priority")
    if on_priority_done:
        on_priority_done()
    run(other_pending, "translate_details")
    return {"failed": failures, "error": first_error, "translated": translated}


def _merge_text(target: dict[str, Any], source: dict[str, Any], key: str) -> None:
    """Fill a missing or poisoned localized field from the bundled catalogue.

    Older caches can contain the Chinese source in an ``*_en`` field. Treat a
    value identical to the corresponding ``*_zh`` field as missing.
    """
    value = target.get(key)
    original = target.get(key[:-3] + "_zh")
    invalid = not value or (
        isinstance(value, str)
        and isinstance(original, str)
        and value.strip() == original.strip()
    )
    if invalid and source.get(key):
        target[key] = source[key]


def merge_english(
    recipes: list[dict[str, Any]], reference: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Carry bundled English text over to a freshly downloaded catalogue.

    The public API only returns the original Chinese text. Without this merge a
    refresh would silently discard the translations shipped with the component.
    """
    by_id = {}
    for recipe in reference:
        try:
            by_id[int(recipe["id"])] = recipe
        except (KeyError, TypeError, ValueError):  # pragma: no cover
            continue
    for recipe in recipes:
        original = by_id.get(int(recipe.get("id", -1)))
        if not original:
            continue
        for key in ("name_en", "description_en", "tips_en"):
            _merge_text(recipe, original, key)
        for collection in ("ingredients", "steps", "foods", "tools"):
            new_items = recipe.get(collection) or []
            old_items = original.get(collection) or []
            for index, item in enumerate(new_items):
                if index >= len(old_items):
                    break
                previous = old_items[index]
                if collection == "foods":
                    _merge_text(item, previous, "name_en")
                    old_subs = previous.get("ingredients") or []
                    for sub_index, sub_item in enumerate(item.get("ingredients") or []):
                        if sub_index < len(old_subs):
                            for key in ("name_en", "quantity_en"):
                                _merge_text(sub_item, old_subs[sub_index], key)
                else:
                    for key in (
                        "name_en",
                        "quantity_en",
                        "content_en",
                    ):
                        _merge_text(item, previous, key)
    return recipes


class RecipeLibrary:
    """Local recipe catalogue with search, favorites and best-effort refresh."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        from homeassistant.helpers.storage import Store

        self.hass = hass
        self.entry = entry
        self.source = entry.options.get(CONF_RECIPE_SOURCE, DEFAULT_RECIPE_SOURCE)
        # The card's language button owns this at runtime; always start in the
        # Home Assistant language mode, ignoring any legacy stored option.
        self.language_mode = DEFAULT_RECIPE_LANGUAGE
        self._cache_store: Store = Store(hass, CACHE_STORE_VERSION, f"{DOMAIN}_recipes")
        self._favorites_store: Store = Store(
            hass, FAVORITES_STORE_VERSION, f"{DOMAIN}_favorites"
        )
        self._translation_store: Store = Store(
            hass, TRANSLATION_STORE_VERSION, f"{DOMAIN}_translations"
        )
        self._recipes: list[dict[str, Any]] = []
        self._by_id: dict[int, dict[str, Any]] = {}
        self._favorites: set[int] = set()
        self.last_refresh: str | None = None
        self.last_error: str | None = None
        self.refresh_phase: str = "idle"
        self.refresh_done: int = 0
        self.refresh_total: int = 0
        self.translation_warning: str | None = None
        self.translation_failures: int = 0
        self.last_query: str = ""
        self.last_search: list[dict[str, Any]] = []
        self.last_recipe: dict[str, Any] | None = None
        self._listeners: set[Callable[[], None]] = set()

    # -- language ---------------------------------------------------------
    @property
    def ha_language(self) -> str:
        return self.hass.config.language or "en"

    @property
    def display_language(self) -> str:
        if self.language_mode == RECIPE_LANGUAGE_ORIGINAL:
            return "zh"
        return language_code(self.ha_language)

    @property
    def language_options(self) -> list[str]:
        ha_label = language_label(self.ha_language)
        original = "中文 (Original)"
        if language_code(self.ha_language) == "zh":
            return [ha_label]
        return [ha_label, original]

    @property
    def language_label(self) -> str:
        if self.language_mode == RECIPE_LANGUAGE_ORIGINAL:
            return "中文 (Original)"
        return language_label(self.ha_language)

    # -- listeners --------------------------------------------------------
    def add_listener(self, update: Callable[[], None]) -> None:
        """Register an entity state refresh callback."""
        self._listeners.add(update)

    def remove_listener(self, update: Callable[[], None]) -> None:
        self._listeners.discard(update)

    def async_update_entities(self) -> None:
        """Push search/detail/favorite changes to recipe entities."""
        for update in tuple(self._listeners):
            update()

    # -- loading ----------------------------------------------------------
    async def async_load(self) -> None:
        bundled = await self.hass.async_add_executor_job(self._load_bundled)
        cached = await self._cache_store.async_load()
        needs_fetch = False
        if isinstance(cached, dict) and cached.get("recipes"):
            self._set_recipes(merge_english(cached["recipes"], bundled))
            self.last_refresh = cached.get("last_refresh")
            needs_fetch = cached.get("version") != _installed_version()
        else:
            self._set_recipes(bundled)
            needs_fetch = True
        favorites = await self._favorites_store.async_load()
        if isinstance(favorites, dict):
            self._favorites = {
                int(value)
                for value in favorites.get("ids") or []
                if str(value).isdigit()
            }
        if self.source == RECIPE_SOURCE_API or (
            self.source == RECIPE_SOURCE_CACHE and needs_fetch
        ):
            self.hass.async_create_task(self.async_refresh())

    @staticmethod
    def _load_bundled() -> list[dict[str, Any]]:
        with BUNDLED_RECIPES.open(encoding="utf-8") as file:
            return json.load(file)

    def _set_recipes(self, recipes: list[dict[str, Any]]) -> None:
        self._recipes = recipes
        self._by_id = {}
        for recipe in recipes:
            try:
                self._by_id[int(recipe["id"])] = recipe
            except (KeyError, TypeError, ValueError):  # pragma: no cover
                continue

    @property
    def recipes(self) -> list[dict[str, Any]]:
        return self._recipes

    def _apply_progress(self, phase: str, done: int, total: int) -> None:
        self.refresh_phase = phase
        self.refresh_done = int(done)
        self.refresh_total = int(total)
        self.async_update_entities()

    def _report_progress(self, phase: str, done: int, total: int) -> None:
        """Update the shared refresh sensor from a worker thread."""
        loop = getattr(self.hass, "loop", None)
        if loop is None:
            self._apply_progress(phase, done, total)
            return
        loop.call_soon_threadsafe(self._apply_progress, phase, done, total)

    def _publish_recipes_from_thread(
        self, recipes: list[dict[str, Any]]
    ) -> None:
        """Expose recipes to search/entities while refresh work continues."""

        def _publish() -> None:
            self._set_recipes(recipes)
            self.async_update_entities()

        loop = getattr(self.hass, "loop", None)
        if loop is None:
            _publish()
            return
        loop.call_soon_threadsafe(_publish)

    # -- refresh ----------------------------------------------------------
    async def async_refresh(self) -> int:
        """Redownload recipes; keep the current catalogue on any failure."""
        stored = await self._translation_store.async_load()
        translations: dict[str, str] = stored if isinstance(stored, dict) else {}
        self._report_progress("start", 0, 0)
        try:
            recipes, translation_stats = await self.hass.async_add_executor_job(
                self._fetch_all,
                translations,
                self._report_progress,
                self._publish_recipes_from_thread,
            )
        except Exception as err:
            self.last_error = str(err)
            _LOGGER.warning("Recipe refresh failed, using existing catalogue: %s", err)
            self._report_progress("idle", 0, 0)
            return len(self._recipes)
        if not recipes:
            self.last_error = "Empty recipe catalogue"
            _LOGGER.warning("Recipe refresh returned no recipes; keeping existing data")
            self._report_progress("idle", 0, 0)
            return len(self._recipes)
        self._set_recipes(recipes)
        self.last_error = None
        self.translation_failures = int(translation_stats.get("failed", 0))
        if self.translation_failures:
            message = (
                translation_stats.get("error") or "Translation service unavailable"
            )
            if self.translation_failures > 1:
                message += f" ({self.translation_failures} strings)"
            self.translation_warning = message
            _LOGGER.warning("Recipe refresh: %s", message)
        else:
            self.translation_warning = None
        self.last_refresh = time.strftime("%Y-%m-%dT%H:%M:%S")
        await self._cache_store.async_save(
            {
                "recipes": recipes,
                "last_refresh": self.last_refresh,
                "version": _installed_version(),
            }
        )
        await self._translation_store.async_save(translations)
        self.async_update_entities()
        self._report_progress("done", len(recipes), len(recipes))
        self._report_progress("idle", 0, 0)
        _LOGGER.info("Refreshed %s recipes from Joyami", len(recipes))
        return len(recipes)

    def _fetch_all(
        self,
        translations: dict[str, str],
        progress: Callable[[str, int, int], None] | None = None,
        publish: Callable[[list[dict[str, Any]]], None] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if progress:
            progress("search", 0, 0)
        search = _api_get(
            _JOYAMI_SEARCH_PATH,
            {
                "keyword": "%",
                "pageNo": "1",
                "pageSize": "5000",
                "model": _JOYAMI_MODEL,
                "language": "zh_CN",
            },
        )
        items = search.get("result") or []
        if not items:
            return [], {"failed": 0, "error": None}
        from concurrent.futures import ThreadPoolExecutor

        recipes: list[dict[str, Any]] = []
        total = len(items)
        with ThreadPoolExecutor(max_workers=6) as pool:
            for index, result in enumerate(pool.map(_api_detail, items), 1):
                if result:
                    recipes.append(result)
                if progress and (index % 10 == 0 or index == total):
                    progress("download", index, total)
        recipes.sort(key=lambda item: int(item["id"]))
        if progress:
            progress("merge", 0, 0)
        merge_english(recipes, self._load_bundled())
        if publish:
            publish(recipes)
        translation_stats = translate_missing(
            recipes,
            translations,
            progress,
            on_priority_done=publish and (lambda: publish(recipes)),
        )
        return recipes, translation_stats

    async def async_translate_recipe(
        self, recipe: dict[str, Any]
    ) -> dict[str, Any]:
        """Translate missing English text for one recipe and persist it."""
        stored = await self._translation_store.async_load()
        translations: dict[str, str] = stored if isinstance(stored, dict) else {}
        stats = await self.hass.async_add_executor_job(
            translate_missing, [recipe], translations
        )
        await self._translation_store.async_save(translations)
        # Keep the on-disk recipe cache in sync so translations survive restarts
        # (json-only mode ignores the translation store at load time).
        cached = await self._cache_store.async_load()
        if isinstance(cached, dict) and cached.get("recipes"):
            cached["recipes"] = self._recipes
            await self._cache_store.async_save(cached)
        failed = int(stats.get("failed", 0))
        translated = int(stats.get("translated", 0))
        self.translation_failures = failed
        if failed:
            message = stats.get("error") or "Translation service unavailable"
            if failed > 1:
                message += f" ({failed} strings)"
            self.translation_warning = message
        else:
            self.translation_warning = None
        self.async_update_entities()
        return {"translated": translated, "failed": failed, "error": stats.get("error")}

    # -- favorites --------------------------------------------------------
    @property
    def favorites(self) -> set[int]:
        return self._favorites

    async def async_set_favorite(self, recipe_id: int, favorite: bool) -> bool:
        if int(recipe_id) not in self._by_id:
            raise ValueError(f"Unknown recipe id: {recipe_id}")
        if favorite:
            self._favorites.add(int(recipe_id))
        else:
            self._favorites.discard(int(recipe_id))
        await self._favorites_store.async_save({"ids": sorted(self._favorites)})
        self.async_update_entities()
        return favorite

    # -- lookup / localization -------------------------------------------
    def resolve(self, value: Any) -> dict[str, Any]:
        if value is None:
            raise ValueError("A recipe id or name is required")
        text = str(value).strip()
        if text.isdigit() and int(text) in self._by_id:
            return self._by_id[int(text)]
        lowered = text.casefold()
        for recipe in self._recipes:
            names = (
                recipe.get("name_zh", ""),
                recipe.get("name_en", ""),
            )
            if any(lowered == str(name).casefold() for name in names):
                return recipe
        for recipe in self._recipes:
            names = (
                recipe.get("name_zh", ""),
                recipe.get("name_en", ""),
            )
            if any(lowered in str(name).casefold() for name in names if name):
                return recipe
        raise ValueError(f"Unknown recipe: {value}")

    def _resolve_language(self, language: str | None) -> str:
        """Resolve a display language selector to a bundled language code."""
        if language in (None, "", "ha"):
            return self.display_language
        if language == RECIPE_LANGUAGE_ORIGINAL:
            return "zh"
        if language in ("zh", "en"):
            return language
        return self.display_language

    def summary(
        self, recipe: dict[str, Any], language: str | None = None
    ) -> dict[str, Any]:
        lang = self._resolve_language(language)
        return {
            "id": int(recipe["id"]),
            "name": _pick(recipe, "name_zh", "name_en", lang),
            "name_zh": recipe.get("name_zh", ""),
            "name_en": recipe.get("name_en", ""),
            "duration": recipe.get("duration"),
            "image": recipe.get("cover_image") or "",
            "favorite": int(recipe["id"]) in self._favorites,
        }

    def detail(
        self, recipe: dict[str, Any], language: str | None = None
    ) -> dict[str, Any]:
        lang = self._resolve_language(language)
        result = self.summary(recipe, lang)
        result.update(
            {
                "description": _pick(recipe, "description_zh", "description_en", lang),
                "tips": _pick(recipe, "tips_zh", "tips_en", lang),
                "default_keep_warm": recipe.get("default_keep_warm"),
                "min_keep_warm": recipe.get("min_keep_warm"),
                "max_keep_warm": recipe.get("max_keep_warm"),
                "cover_image": recipe.get("cover_image") or "",
                "ingredients": [
                    {
                        "name": _pick(item, "name_zh", "name_en", lang),
                        "quantity": _pick(item, "quantity_zh", "quantity_en", lang),
                    }
                    for item in recipe.get("ingredients") or []
                ],
                "steps": [
                    {
                        "content": _pick(item, "content_zh", "content_en", lang),
                        "image": item.get("image") or "",
                    }
                    for item in recipe.get("steps") or []
                ],
                "foods": [
                    {
                        "name": _pick(food, "name_zh", "name_en", lang),
                        "ingredients": [
                            {
                                "name": _pick(item, "name_zh", "name_en", lang),
                                "quantity": _pick(
                                    item, "quantity_zh", "quantity_en", lang
                                ),
                            }
                            for item in food.get("ingredients") or []
                        ],
                    }
                    for food in recipe.get("foods") or []
                ],
                "tools": [
                    {
                        "name": _pick(item, "name_zh", "name_en", lang),
                        "image": item.get("image") or "",
                    }
                    for item in recipe.get("tools") or []
                ],
                "cookcode": recipe.get("cookcode") or "",
                "runnable_cookcode": recipe.get("runnable_cookcode") or "",
            }
        )
        self.last_recipe = result
        return result

    def search(
        self,
        query: str,
        limit: int = 20,
        favorites_only: bool = False,
        language: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search names, ingredients and descriptions in Chinese or English."""
        lang = language or self.display_language
        needle = (query or "").strip().casefold()
        self.last_query = str(query or "")
        matches: list[tuple[int, dict[str, Any]]] = []
        for recipe in self._recipes:
            if favorites_only and int(recipe["id"]) not in self._favorites:
                continue
            if not needle:
                matches.append((0, recipe))
                continue
            score = 0
            name_zh = str(recipe.get("name_zh") or "").casefold()
            name_en = str(recipe.get("name_en") or "").casefold()
            if needle == name_zh or needle == name_en:
                score = 100
            elif needle in name_zh or needle in name_en:
                score = 50
            else:
                haystack = [
                    str(recipe.get("description_zh") or ""),
                    str(recipe.get("description_en") or ""),
                ]
                for item in recipe.get("ingredients") or []:
                    haystack += [
                        str(item.get("name_zh") or ""),
                        str(item.get("name_en") or ""),
                    ]
                for food in recipe.get("foods") or []:
                    haystack += [
                        str(food.get("name_zh") or ""),
                        str(food.get("name_en") or ""),
                    ]
                    for item in food.get("ingredients") or []:
                        haystack += [
                            str(item.get("name_zh") or ""),
                            str(item.get("name_en") or ""),
                        ]
                if any(needle in value.casefold() for value in haystack):
                    score = 10
            if score:
                matches.append((score, recipe))
        matches.sort(key=lambda pair: (-pair[0], int(pair[1]["id"])))
        result = [
            self.summary(recipe, lang)
            for _, recipe in matches[: max(0, min(limit, len(matches)))]
        ]
        self.last_search = result
        self.async_update_entities()
        return result
