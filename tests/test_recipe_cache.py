"""Tests for the cache-first recipe refresh policy."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import custom_components.xiaomi_cooker_local.recipes as recipes_module
from custom_components.xiaomi_cooker_local.recipes import RecipeLibrary


def _library(cache, source, monkeypatch):
    monkeypatch.setattr(recipes_module, "_installed_version", lambda: "0.4.2")
    monkeypatch.setattr(
        recipes_module, "merge_english", lambda cached, bundled: cached
    )
    library = object.__new__(RecipeLibrary)
    library.hass = SimpleNamespace(
        async_add_executor_job=AsyncMock(side_effect=lambda fn: fn()),
        async_create_task=Mock(side_effect=lambda coro: coro.close()),
        config=SimpleNamespace(language="en"),
    )
    library.source = source
    library._cache_store = SimpleNamespace(async_load=AsyncMock(return_value=cache))
    library._favorites_store = SimpleNamespace(
        async_load=AsyncMock(return_value={"ids": []})
    )
    library._recipes = []
    library._by_id = {}
    library._favorites = set()
    library.last_refresh = None
    return library


def _cached(version):
    recipes = [{"id": 1, "name_zh": "饭", "name_en": "rice"}]
    return {"recipes": recipes, "version": version}


def test_cache_source_with_current_version_does_not_refresh(monkeypatch) -> None:
    library = _library(_cached("0.4.2"), "cache", monkeypatch)

    asyncio.run(library.async_load())

    library.hass.async_create_task.assert_not_called()
    assert library.last_refresh is None


def test_cache_source_refreshes_on_first_run(monkeypatch) -> None:
    library = _library(None, "cache", monkeypatch)

    asyncio.run(library.async_load())

    library.hass.async_create_task.assert_called_once()


def test_cache_source_refreshes_after_version_change(monkeypatch) -> None:
    library = _library(_cached("0.4.1"), "cache", monkeypatch)

    asyncio.run(library.async_load())

    library.hass.async_create_task.assert_called_once()


def test_every_start_source_always_refreshes(monkeypatch) -> None:
    library = _library(_cached("0.4.2"), "api", monkeypatch)

    asyncio.run(library.async_load())

    library.hass.async_create_task.assert_called_once()


def test_bundled_only_source_never_refreshes(monkeypatch) -> None:
    library = _library(_cached("0.4.1"), "json", monkeypatch)

    asyncio.run(library.async_load())

    library.hass.async_create_task.assert_not_called()
