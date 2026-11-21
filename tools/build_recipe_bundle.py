"""Build the bundled recipe catalogue for the Xiaomi Cooker Local integration.

Fetches the public Joyami recipe catalogue, resolves full details for every
chunmi.cooker.normalcd1 recipe, translates the Chinese text to English once
(at build time, not in Home Assistant) and writes ``recipes.json`` next to the
integration code.

Usage::

    python tools/build_recipe_bundle.py

The runtime integration never calls this script; the generated JSON is shipped
with the component. A refreshed copy can also be downloaded at runtime via the
``refresh_recipes`` service, with this bundled file as the fallback.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

import requests

APP_ID = "202007190935014"
BASE = "https://gateway.joyami.com"
MODEL = "chunmi.cooker.normalcd1"
SEARCH_PATH = "/microwaveoven/index/search"
DETAIL_PATH = "/microwaveoven/index/getRecipeDetailById"
TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "custom_components" / "xiaomi_cooker_local" / "recipes.json"
TRANSLATION_CACHE = ROOT / "capture" / "translation_cache.json"

TRANSLATABLE = (
    "name",
    "description",
    "tips",
    "ingredients.name",
    "ingredients.quantity",
    "steps.content",
    "foods.foodName",
    "foods.ingredients.name",
    "foods.ingredients.quantity",
    "recipeTools.toolName",
)


def signed_headers(method: str, path: str, vid: str = "1") -> dict[str, str]:
    """Return headers signed the same way the Mi Home plugin signs them."""
    timestamp = str(int(time.time() * 1000))
    minute = int(timestamp) // 60000
    nonce = base64.urlsafe_b64encode(
        os.urandom(8) + minute.to_bytes(4, "big")
    ).decode()
    payload = f"{APP_ID}&{timestamp}&{nonce}&{method}&{path}"
    signature = base64.urlsafe_b64encode(
        hashlib.sha256(payload.encode()).digest()
    ).decode()
    return {
        "appid": APP_ID,
        "version": f"{MODEL}: 9",
        "timestamp": timestamp,
        "nonce": nonce,
        "vid": vid,
        "signature": signature,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def api_get(path: str, params: dict[str, Any], attempts: int = 3) -> dict[str, Any]:
    """GET a Joyami endpoint, retrying transient gateway errors."""
    url = BASE + path + "?" + urlencode(params)
    last: Exception | None = None
    for _ in range(attempts):
        try:
            response = requests.get(
                url, headers=signed_headers("GET", path), timeout=60
            )
            if response.status_code == 200:
                return response.json()
            last = RuntimeError(f"HTTP {response.status_code}: {response.text[:120]}")
        except Exception as err:  # pragma: no cover - network dependent
            last = err
        time.sleep(1)
    raise RuntimeError(f"Joyami request failed for {path}: {last}")


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
    """Install a cloud recipe into the cooker's temporary slot 05."""
    data = bytearray(bytes.fromhex(cookcode))
    if len(data) != 133:
        raise ValueError(f"Unexpected cookcode length: {len(data)} bytes")
    data[2] = 0x05
    data[7] &= 0x7F
    data[-2:] = crc16_xmodem(data[:-2]).to_bytes(2, "big")
    return data.hex()


def translation_cache() -> dict[str, str]:
    if TRANSLATION_CACHE.exists():
        try:
            return json.loads(TRANSLATION_CACHE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):  # pragma: no cover
            pass
    return {}


def translate(text: str, cache: dict[str, str]) -> str:
    """Translate Chinese to English. Never store Chinese as a translation."""
    if not text or not text.strip():
        return ""
    key = text.strip()
    cached = cache.get(key)
    if cached is not None and cached != key:
        return cached
    url = TRANSLATE_URL + "?client=gtx&sl=zh-CN&tl=en&dt=t&q=" + quote(key)
    for attempt in range(6):
        try:
            response = requests.get(url, timeout=30)
            if response.status_code == 429:
                time.sleep(min(2**attempt, 20))
                continue
            if response.status_code != 200:
                time.sleep(1 + attempt)
                continue
            payload = response.json()
            result = "".join(
                part[0] for part in (payload[0] or []) if part and part[0]
            ).strip()
            if result and result != key:
                cache[key] = result
                return result
        except Exception:  # pragma: no cover - network dependent
            pass
        time.sleep(1 + attempt)
    # Record the attempt as empty, never as the Chinese source text itself.
    cache[key] = ""
    return ""


def collect_strings(recipe: dict[str, Any]) -> set[str]:
    found: set[str] = set()
    for key in ("name", "description", "tips"):
        value = recipe.get(key)
        if isinstance(value, str) and any("\u4e00" <= c <= "\u9fff" for c in value):
            found.add(value)
    for ingredient in recipe.get("ingredients") or []:
        for key in ("name", "quantity"):
            value = ingredient.get(key)
            if isinstance(value, str) and any("\u4e00" <= c <= "\u9fff" for c in value):
                found.add(value)
    for step in recipe.get("steps") or []:
        value = step.get("content")
        if isinstance(value, str) and any("\u4e00" <= c <= "\u9fff" for c in value):
            found.add(value)
    for food in recipe.get("foods") or []:
        value = food.get("foodName")
        if isinstance(value, str) and any("\u4e00" <= c <= "\u9fff" for c in value):
            found.add(value)
        for ingredient in food.get("ingredients") or []:
            for key in ("name", "quantity"):
                value = ingredient.get(key)
                if isinstance(value, str) and any(
                    "\u4e00" <= c <= "\u9fff" for c in value
                ):
                    found.add(value)
    for tool in recipe.get("recipeTools") or []:
        value = tool.get("toolName")
        if isinstance(value, str) and any("\u4e00" <= c <= "\u9fff" for c in value):
            found.add(value)
    return found


def localize_recipe(recipe: dict[str, Any], cache: dict[str, str]) -> dict[str, Any]:
    def t(value: Any) -> str:
        return translate(value, cache) if isinstance(value, str) else ""

    ingredients = []
    for item in recipe.get("ingredients") or []:
        ingredients.append(
            {
                "name_zh": item.get("name") or "",
                "name_en": t(item.get("name")),
                "quantity_zh": item.get("quantity") or "",
                "quantity_en": t(item.get("quantity")),
            }
        )
    steps = []
    for item in recipe.get("steps") or []:
        steps.append(
            {
                "content_zh": item.get("content") or "",
                "content_en": t(item.get("content")),
                "image": item.get("coverImg") or "",
            }
        )
    foods = []
    for food in recipe.get("foods") or []:
        foods.append(
            {
                "name_zh": food.get("foodName") or "",
                "name_en": t(food.get("foodName")),
                "ingredients": [
                    {
                        "name_zh": item.get("name") or "",
                        "name_en": t(item.get("name")),
                        "quantity_zh": item.get("quantity") or "",
                        "quantity_en": t(item.get("quantity")),
                    }
                    for item in food.get("ingredients") or []
                ],
            }
        )
    tools = []
    for tool in recipe.get("recipeTools") or []:
        tools.append(
            {
                "name_zh": tool.get("toolName") or "",
                "name_en": t(tool.get("toolName")),
                "image": tool.get("toolImg") or "",
            }
        )
    return {
        "id": recipe["id"],
        "name_zh": recipe.get("name") or "",
        "name_en": t(recipe.get("name")),
        "description_zh": recipe.get("description") or "",
        "description_en": t(recipe.get("description")),
        "tips_zh": recipe.get("tips") or "",
        "tips_en": t(recipe.get("tips")),
        "duration": recipe.get("duration"),
        "default_keep_warm": recipe.get("defaultKeepWarmDuration"),
        "min_keep_warm": recipe.get("minKeepWarmDuration"),
        "max_keep_warm": recipe.get("maxKeepWarmDuration"),
        "cover_image": recipe.get("coverImg") or "",
        "ingredients": ingredients,
        "steps": steps,
        "foods": foods,
        "tools": tools,
        "cookcode": recipe["cookcode"],
        "runnable_cookcode": make_runnable(recipe["cookcode"]),
    }


def fetch_detail(item: dict[str, Any]) -> dict[str, Any] | None:
    try:
        result = api_get(
            DETAIL_PATH,
            {
                "recipeId": item["id"],
                "deviceId": "1",
                "model": MODEL,
                "menuType": "1",
                "language": "zh_CN",
            },
        ).get("result") or {}
        script = next(
            (
                model.get("cookScript")
                for model in result.get("cookModels") or []
                if model.get("model") == MODEL
            and len(model.get("cookScript") or "") == 266
            ),
            None,
        )
        if not script:
            return None
        return {
            "id": item["id"],
            "name": result.get("name") or item.get("name"),
            "description": result.get("description") or "",
            "tips": result.get("tips") or "",
            "duration": result.get("duration") or item.get("duration"),
            "defaultKeepWarmDuration": result.get("defaultKeepWarmDuration"),
            "minKeepWarmDuration": result.get("minKeepWarmDuration"),
            "maxKeepWarmDuration": result.get("maxKeepWarmDuration"),
            "coverImg": result.get("coverImg") or item.get("coverImg"),
            "ingredients": result.get("ingredients") or [],
            "steps": result.get("steps") or [],
            "foods": result.get("foods") or [],
            "recipeTools": result.get("recipeTools") or [],
            "cookcode": script,
        }
    except Exception as err:  # pragma: no cover - network dependent
        print(f"  detail {item.get('id')} failed: {err}")
        return None


def main() -> None:
    print("Fetching catalogue…")
    search = api_get(
        SEARCH_PATH,
        {
            "keyword": "%",
            "pageNo": "1",
            "pageSize": "5000",
            "model": MODEL,
            "language": "zh_CN",
        },
    )
    items = search.get("result") or []
    print(f"  {len(items)} catalogue entries")

    print("Fetching details…")
    details: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(fetch_detail, item) for item in items]
        for index, future in enumerate(as_completed(futures), 1):
            detail = future.result()
            if detail:
                details.append(detail)
            if index % 100 == 0:
                print(f"  {index}/{len(items)}")
    details.sort(key=lambda item: item["id"])
    print(f"  {len(details)} recipes with cd1 cookcodes")

    cache = translation_cache()
    strings: set[str] = set()
    for detail in details:
        strings |= collect_strings(detail)
    print(f"Translating {len(strings)} unique Chinese strings…")
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(translate, text, cache): text for text in strings}
        for index, future in enumerate(as_completed(futures), 1):
            future.result()
            if index % 250 == 0:
                print(f"  {index}/{len(strings)}")
    TRANSLATION_CACHE.parent.mkdir(parents=True, exist_ok=True)
    TRANSLATION_CACHE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8"
    )

    bundle = [localize_recipe(detail, cache) for detail in details]
    OUTPUT.write_text(
        json.dumps(bundle, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    size = OUTPUT.stat().st_size / 1024
    print(f"Wrote {OUTPUT} ({size:.0f} KiB, {len(bundle)} recipes)")


if __name__ == "__main__":
    main()
