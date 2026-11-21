"""Tests for the searchable card registration."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.components.lovelace.const import LOVELACE_DATA, MODE_STORAGE

from custom_components.xiaomi_cooker_local import frontend
from custom_components.xiaomi_cooker_local.const import DOMAIN

_ENTITY_LOOKUPS = frontend._ENTITY_LOOKUPS


class FakeResources:
    def __init__(self, items):
        self.items = items
        self.created = []
        self._async_ensure_loaded = AsyncMock()
        self.async_create_item = AsyncMock(side_effect=self.created.append)

    def async_items(self):
        return self.items


def _hass(resources=None, registered=False):
    data = {}
    if resources is not None:
        data[LOVELACE_DATA] = SimpleNamespace(
            resource_mode=MODE_STORAGE, resources=resources
        )
    if registered:
        data[frontend._REGISTERED] = True
    return SimpleNamespace(
        data=data,
        http=SimpleNamespace(async_register_static_paths=AsyncMock()),
        async_create_task=Mock(side_effect=lambda coro: coro.close()),
    )


def test_register_card_adds_resource_once() -> None:
    resources = FakeResources([])
    hass = _hass(resources)

    asyncio.run(frontend.async_register_card(hass))

    hass.http.async_register_static_paths.assert_awaited_once()
    resources._async_ensure_loaded.assert_awaited_once()
    resources.async_create_item.assert_awaited_once_with(
        {"res_type": "module", "url": frontend.CARD_URL}
    )
    assert hass.data[frontend._REGISTERED]

    asyncio.run(frontend.async_register_card(hass))
    resources.async_create_item.assert_awaited_once()


def test_register_card_skips_existing_resource() -> None:
    resources = FakeResources([{"url": frontend.CARD_URL}])
    hass = _hass(resources)

    asyncio.run(frontend.async_register_card(hass))

    resources.async_create_item.assert_not_awaited()


def test_register_card_without_lovelace_does_not_mark_registered() -> None:
    hass = _hass(resources=None)

    asyncio.run(frontend.async_register_card(hass))

    assert frontend._REGISTERED not in hass.data


def test_cookers_resolves_native_entities() -> None:
    runtime = {DOMAIN: {"entry-1": {}}}
    hass = SimpleNamespace(data=runtime)

    def device_id(identifiers):
        return SimpleNamespace(id="device-1", name="Kitchen cooker")

    class EntityRegistry:
        def async_get_entity_id(self, platform, domain, unique_id):
            return f"{platform}.cooker_{unique_id.split('_', 1)[1]}"

    with (
        patch.object(frontend.dr, "async_get", return_value=SimpleNamespace(
            async_get_device=device_id
        )),
        patch.object(frontend.er, "async_get", return_value=EntityRegistry()),
    ):
        cookers = frontend._cookers(hass)

    assert len(cookers) == 1
    cooker = cookers[0]
    assert cooker["device_id"] == "device-1"
    assert cooker["name"] == "Kitchen cooker"
    assert cooker["entities"]["query"] == "text.cooker_recipe_query"
    assert cooker["entities"]["status"] == "sensor.cooker_status_name"
    assert len(cooker["entities"]) == len(_ENTITY_LOOKUPS)
