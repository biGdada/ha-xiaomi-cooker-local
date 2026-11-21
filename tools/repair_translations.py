"""Repair Chinese text that was cached as if it were an English translation.

The original build script wrote the source string into the ``*_en`` fields when
Google's translate endpoint rate-limited it. This tool re-translates those
strings politely (with delays and backoff), and rewrites ``recipes.json`` and
the translation cache incrementally so interrupted runs keep their progress.

Safe to re-run: already-correct entries are skipped. English fields are never
left containing Chinese; a failed translation becomes an empty field so the
card falls back to the Chinese source instead of displaying it as English.

Usage::

    python tools/repair_translations.py
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "custom_components" / "xiaomi_cooker_local" / "recipes.json"
CACHE = ROOT / "capture" / "translation_cache.json"
TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"

REQUEST_DELAY = 2.0  # Seconds between batches, to stay under the rate limit.
RATE_LIMIT_WAIT = 60  # Seconds between checks while the endpoint is blocked.
MAX_RATE_RETRIES = 4  # Checks per batch before a longer coordinated wait.
MAX_WAIT_MINUTES = 180  # Overall cap on waiting for the endpoint to recover.

RECIPE_KEYS = ("name_en", "description_en", "tips_en")
ITEM_KEYS = ("name_en", "content_en", "quantity_en")
COLLECTIONS = ("ingredients", "steps", "foods", "tools")


def has_chinese(value: object) -> bool:
    return isinstance(value, str) and any("\u4e00" <= c <= "\u9fff" for c in value)


def bad_strings(bundle: list[dict]) -> set[str]:
    found: set[str] = set()

    def scan(item: dict, keys: tuple[str, ...]) -> None:
        for key in keys:
            value = item.get(key)
            if has_chinese(value):
                found.add(str(value).strip())

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
    return found


def wait_until_available() -> bool:
    """Poll a tiny request until Google stops returning HTTP 429."""
    deadline = time.monotonic() + MAX_WAIT_MINUTES * 60
    check = 0
    probe = TRANSLATE_URL + "?client=gtx&sl=zh-CN&tl=en&dt=t&q=" + quote("米饭")
    while time.monotonic() < deadline:
        try:
            response = requests.get(
                probe, timeout=15, headers={"User-Agent": "Mozilla/5.0"}
            )
            if response.status_code == 200:
                print("  translate endpoint available", flush=True)
                return True
            check += 1
            if check % 5 == 0:
                remaining = round((deadline - time.monotonic()) / 60)
                print(
                    f"  still rate limited ({check} checks, ~{remaining} min left)",
                    flush=True,
                )
        except Exception as err:  # pragma: no cover - network errors
            print(f"  probe error: {err}", flush=True)
        time.sleep(RATE_LIMIT_WAIT)
    return False


def request_translation(texts: list[str]) -> dict[str, str]:
    """Translate a batch of newline-safe strings, keyed by source."""
    url = TRANSLATE_URL + "?client=gtx&sl=zh-CN&tl=en&dt=t&q=" + quote(
        "\n".join(texts)
    )
    for _ in range(MAX_RATE_RETRIES):
        try:
            response = requests.get(
                url, timeout=30, headers={"User-Agent": "Mozilla/5.0"}
            )
            if response.status_code == 429:
                if not wait_until_available():
                    return {}
                continue
            if response.status_code != 200:
                time.sleep(5)
                continue
            segments = (response.json() or [[]])[0] or []
            if len(segments) != len(texts):
                return {}
            result: dict[str, str] = {}
            for source, segment in zip(texts, segments, strict=False):
                translated = str(segment[0] or "").rstrip("\n").strip()
                original = str(segment[1] or "").rstrip("\n").strip()
                if original != source.strip():
                    return {}
                result[source] = "" if translated == source else translated
            return result
        except Exception as err:  # pragma: no cover - network/parse errors
            print(f"  request error: {err}", flush=True)
            time.sleep(10)
    return {}


def apply(
    bundle: list[dict], cache: dict[str, str]
) -> int:
    """Replace Chinese English-fields with cached text (or an empty value)."""
    changed = 0

    def fix(item: dict, keys: tuple[str, ...]) -> None:
        nonlocal changed
        for key in keys:
            value = item.get(key)
            if has_chinese(value):
                replacement = cache.get(str(value).strip(), "")
                if has_chinese(replacement):
                    replacement = ""
                item[key] = replacement
                changed += 1

    for recipe in bundle:
        fix(recipe, RECIPE_KEYS)
        for collection in COLLECTIONS:
            for item in recipe.get(collection) or []:
                if not isinstance(item, dict):
                    continue
                fix(item, ITEM_KEYS)
                for child in item.get("ingredients") or []:
                    if isinstance(child, dict):
                        fix(child, ITEM_KEYS)
    return changed


def save(bundle: list[dict], cache: dict[str, str]) -> None:
    OUTPUT.write_text(
        json.dumps(bundle, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    CACHE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8"
    )


def main() -> None:
    bundle = json.loads(OUTPUT.read_text(encoding="utf-8"))
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    targets = bad_strings(bundle)

    # First, apply every translation already in the cache. No network needed.
    changed = apply(bundle, cache)
    if changed:
        save(bundle, cache)
    print(
        f"Applied {changed} cached translations; "
        f"{len(bad_strings(bundle))} Chinese values remain in _en fields",
        flush=True,
    )

    pending = sorted(
        s for s in targets if not cache.get(s) or has_chinese(cache.get(s))
    )
    print(f"{len(targets)} poisoned strings, {len(pending)} to translate", flush=True)

    batch: list[str] = []
    size = 0
    done = 0
    since_save = 0

    def flush() -> None:
        nonlocal batch, size, done, since_save
        if not batch:
            return
        result = request_translation(batch)
        if not result and len(batch) > 1:
            # Split once rather than firing one request per string.
            middle = len(batch) // 2
            result = request_translation(batch[:middle])
            result.update(request_translation(batch[middle:]))
        for text in batch:
            value = result.get(text, "")
            cache[text] = "" if has_chinese(value) else value
            done += 1
        batch, size = [], 0
        since_save += 1
        if since_save >= 10 or done == len(pending):
            apply(bundle, cache)
            save(bundle, cache)
            since_save = 0
            remaining = len(bad_strings(bundle))
            print(f"  {done}/{len(pending)} done; {remaining} left", flush=True)
        time.sleep(REQUEST_DELAY)

    for text in pending:
        if "\n" in text or size + len(text) > 1200 or len(batch) >= 20:
            flush()
        if "\n" in text:
            cache[text] = request_translation([text]).get(text, "")
            if has_chinese(cache[text]):
                cache[text] = ""
            done += 1
            time.sleep(REQUEST_DELAY)
            continue
        batch.append(text)
        size += len(text) + 1
    flush()

    apply(bundle, cache)
    save(bundle, cache)
    remaining = len(bad_strings(bundle))
    print(
        f"Finished: {len(pending)} attempted; {remaining} Chinese values "
        f"remain in _en fields",
        flush=True,
    )


if __name__ == "__main__":
    main()
