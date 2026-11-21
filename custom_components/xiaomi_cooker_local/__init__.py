"""The Xiaomi Rice Cooker (local miio) integration."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from functools import partial
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_HOST,
    CONF_NAME,
    EVENT_HOMEASSISTANT_STARTED,
)
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import (
    config_validation as cv,
)
from homeassistant.helpers import (
    device_registry as dr,
)
from homeassistant.helpers import (
    entity_registry as er,
)

from .client import CookerClient
from .const import (
    ATTR_DEVICE_ID,
    ATTR_FAVORITES_ONLY,
    ATTR_LANGUAGE,
    ATTR_LIMIT,
    ATTR_METHOD,
    ATTR_PARAMETERS,
    ATTR_PROFILE,
    ATTR_QUERY,
    ATTR_RECIPE,
    CONF_MODEL,
    CONF_PROFILES,
    CONF_SCAN_INTERVAL,
    CONF_TIMEOUT,
    DATA_ACTIVE_RECIPE_ID,
    DATA_CLIENT,
    DATA_COORDINATOR,
    DATA_LAST_DUMP,
    DATA_RECIPE_QUERY,
    DATA_RECIPES,
    DATA_SELECTED_PROFILE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
    MODEL_CD1,
    PLATFORMS,
    SERVICE_ADD_FAVORITE,
    SERVICE_DUMP,
    SERVICE_GET_RECIPE,
    SERVICE_GET_TEMPERATURE_HISTORY,
    SERVICE_LIST_FAVORITES,
    SERVICE_RAW_COMMAND,
    SERVICE_REFRESH_RECIPES,
    SERVICE_REMOVE_FAVORITE,
    SERVICE_SEARCH_RECIPES,
    SERVICE_SET_MENU,
    SERVICE_SET_RECIPE_LANGUAGE,
    SERVICE_SET_SETTINGS,
    SERVICE_SET_TIMEOUTS,
    SERVICE_START,
    SERVICE_START_RECIPE,
    SERVICE_STOP,
    SERVICE_TRANSLATE_RECIPE,
)
from .coordinator import CookerDataUpdateCoordinator
from .frontend import async_register_card, async_register_card_config_ws
from .parsing import TIMEOUT_FIELDS, WRITABLE_SETTINGS
from .profiles import profiles_for_model, resolve_profile
from .recipes import RecipeLibrary
from .service_schema import SERVICE_SCHEMAS

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


def _runtime(hass: HomeAssistant) -> dict[str, dict[str, Any]]:
    return hass.data.setdefault(DOMAIN, {})


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register the searchable custom card."""
    async_register_card_config_ws(hass)

    async def _async_startup(event: Any) -> None:
        await async_register_card(hass)

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _async_startup)
    if hass.is_running:
        hass.async_create_task(async_register_card(hass))
    return True


def _as_list(value: Any) -> list[Any]:
    """Normalize HA target fields, which may be a scalar or a list."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _entry_for_call(hass: HomeAssistant, call: ServiceCall) -> ConfigEntry:
    """Resolve the targeted config entry, falling back to a single configured cooker."""
    runtime = _runtime(hass)
    for device_id in _as_list(call.data.get(ATTR_DEVICE_ID)):
        device = dr.async_get(hass).async_get(device_id)
        if device:
            for entry_id in device.config_entries:
                if entry_id in runtime:
                    return hass.config_entries.async_get_entry(entry_id)

    entity_ids = _as_list(call.data.get(ATTR_ENTITY_ID))
    if entity_ids:
        entity_registry = er.async_get(hass)
        for entity_id in entity_ids:
            entity = entity_registry.async_get(entity_id)
            if entity and entity.config_entry_id in runtime:
                return hass.config_entries.async_get_entry(entity.config_entry_id)

    entries = [
        hass.config_entries.async_get_entry(entry_id)
        for entry_id in runtime
        if hass.config_entries.async_get_entry(entry_id) is not None
    ]
    if len(entries) == 1:
        return entries[0]
    raise HomeAssistantError(
        "Target a cooker device_id when multiple cookers are configured"
    )


def _coordinator(hass: HomeAssistant, call: ServiceCall) -> CookerDataUpdateCoordinator:
    entry = _entry_for_call(hass, call)
    return _runtime(hass)[entry.entry_id][DATA_COORDINATOR]


def _client(hass: HomeAssistant, call: ServiceCall) -> CookerClient:
    entry = _entry_for_call(hass, call)
    return _runtime(hass)[entry.entry_id][DATA_CLIENT]


def _library(hass: HomeAssistant, call: ServiceCall) -> RecipeLibrary:
    entry = _entry_for_call(hass, call)
    return _runtime(hass)[entry.entry_id][DATA_RECIPES]


def _recipe_arg(call: ServiceCall) -> Any:
    """Return the recipe ID supplied by the caller (always explicit in the card)."""
    value = call.data.get(ATTR_RECIPE)
    if value is None:
        raise HomeAssistantError("Select a recipe ID first")
    return value


def _resolve_profile(hass: HomeAssistant, call: ServiceCall, value: str | None) -> str:
    entry = _entry_for_call(hass, call)
    client = _client(hass, call)
    if client.model == MODEL_CD1:
        # cd1 uses small integer cook modes instead of classic hex profiles.
        runtime = _runtime(hass)[entry.entry_id]
        return value or runtime.get(DATA_SELECTED_PROFILE) or "Quick Cook"
    if not value:
        profiles = profiles_for_model(entry.data.get(CONF_MODEL))
        if not profiles:
            raise HomeAssistantError("No profiles available for this model")
        return profiles[0]["profile"]
    return resolve_profile(
        entry.data.get(CONF_MODEL), value, entry.options.get(CONF_PROFILES)
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one rice cooker from a config entry."""
    data = {**entry.data, **entry.options}
    client = CookerClient(
        host=data[CONF_HOST],
        token=data["token"],
        model=data.get(CONF_MODEL) or None,
        timeout=data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
    )

    if not client.model:
        try:
            info = await hass.async_add_executor_job(client.probe)
        except Exception as err:
            _LOGGER.warning("Could not auto-detect the cooker model: %s", err)
        else:
            detected = info.get("model")
            if detected and detected != "unknown":
                client.model = detected
                hass.config_entries.async_update_entry(
                    entry, data={**entry.data, CONF_MODEL: detected}
                )

    coordinator = CookerDataUpdateCoordinator(
        hass,
        client,
        name=data.get(CONF_NAME) or "Rice Cooker",
        update_interval=timedelta(
            seconds=data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        ),
        config_entry=entry,
    )
    await coordinator.async_config_entry_first_refresh()

    library = RecipeLibrary(hass, entry)
    await library.async_load()

    _runtime(hass)[entry.entry_id] = {
        DATA_CLIENT: client,
        DATA_COORDINATOR: coordinator,
        DATA_SELECTED_PROFILE: None,
        DATA_RECIPES: library,
        DATA_RECIPE_QUERY: "",
        DATA_ACTIVE_RECIPE_ID: None,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        runtime = _runtime(hass)
        state = runtime.pop(entry.entry_id, {})
        client = state.get(DATA_CLIENT)
        if client:
            await hass.async_add_executor_job(client.close)
        if not runtime:
            _async_remove_services(hass)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


@callback
def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_START):
        return

    async def start(call: ServiceCall) -> None:
        entry = _entry_for_call(hass, call)
        runtime = _runtime(hass)[entry.entry_id]
        client = runtime[DATA_CLIENT]
        profile = _resolve_profile(hass, call, call.data.get(ATTR_PROFILE))
        runtime[DATA_ACTIVE_RECIPE_ID] = None
        await hass.async_add_executor_job(client.start, profile)
        _LOGGER.info("Started cooking profile %s", profile[:16])
        await runtime[DATA_COORDINATOR].async_refresh_after_command()

    async def stop(call: ServiceCall) -> None:
        entry = _entry_for_call(hass, call)
        runtime = _runtime(hass)[entry.entry_id]
        client = runtime[DATA_CLIENT]
        runtime[DATA_ACTIVE_RECIPE_ID] = None
        await hass.async_add_executor_job(client.stop)
        await runtime[DATA_COORDINATOR].async_refresh_after_command()

    async def raw_command(call: ServiceCall) -> None:
        client = _client(hass, call)
        result = await hass.async_add_executor_job(
            partial(
                client.raw_command,
                call.data[ATTR_METHOD],
                call.data.get(ATTR_PARAMETERS, []),
            )
        )
        _LOGGER.info(
            "Raw command %s returned: %s", call.data[ATTR_METHOD], result
        )

    async def dump(call: ServiceCall) -> dict[str, Any]:
        entry = _entry_for_call(hass, call)
        runtime = _runtime(hass)[entry.entry_id]
        client = runtime[DATA_CLIENT]
        coordinator = runtime[DATA_COORDINATOR]
        info = await hass.async_add_executor_job(client.info)
        raw = await hass.async_add_executor_job(client.raw_status)
        snapshot = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "entry_id": entry.entry_id,
            "host": entry.data.get(CONF_HOST),
            "model": client.model,
            "info": info,
            "raw_status": raw,
            "parsed_status": coordinator.data.parsed if coordinator.data else None,
        }
        path = hass.config.path(
            ".storage",
            f"xiaomi_cooker_local_dump_{entry.entry_id}_{int(datetime.now().timestamp())}.json",
        )

        def _write() -> None:
            with open(path, "w", encoding="utf-8") as file:
                json.dump(snapshot, file, indent=2, ensure_ascii=False, default=str)

        await hass.async_add_executor_job(_write)
        runtime[DATA_LAST_DUMP] = snapshot
        _LOGGER.info("Cooker dump written to %s", path)
        return {"path": path, **snapshot}

    async def set_menu(call: ServiceCall) -> None:
        client = _client(hass, call)
        profile = _resolve_profile(hass, call, call.data[ATTR_PROFILE])
        await hass.async_add_executor_job(client.set_menu, profile)
        await _coordinator(hass, call).async_request_refresh()

    async def set_settings(call: ServiceCall) -> None:
        client = _client(hass, call)
        updates = {
            name: call.data[name]
            for name in WRITABLE_SETTINGS
            if name in call.data
        }
        if not updates:
            return
        await hass.async_add_executor_job(client.update_flags, updates)
        await _coordinator(hass, call).async_request_refresh()

    async def set_timeouts(call: ServiceCall) -> None:
        client = _client(hass, call)
        updates = {
            name: call.data[name] for name in TIMEOUT_FIELDS if name in call.data
        }
        if not updates:
            return
        await hass.async_add_executor_job(client.update_timeouts, updates)
        await _coordinator(hass, call).async_request_refresh()

    async def get_temperature_history(call: ServiceCall) -> dict[str, Any]:
        client = _client(hass, call)
        temperatures = await hass.async_add_executor_job(client.temperature_history)
        return {"temperatures": temperatures}

    async def search_recipes(call: ServiceCall) -> dict[str, Any]:
        library = _library(hass, call)
        entry = _entry_for_call(hass, call)
        query = call.data.get(ATTR_QUERY) or _runtime(hass)[entry.entry_id].get(
            DATA_RECIPE_QUERY, ""
        )
        return {
            "recipes": library.search(
                query,
                limit=call.data.get(ATTR_LIMIT, 20),
                favorites_only=call.data.get(ATTR_FAVORITES_ONLY, False),
            ),
            "language": library.display_language,
            "total": len(library.recipes),
        }

    async def get_recipe(call: ServiceCall) -> dict[str, Any]:
        library = _library(hass, call)
        detail = library.detail(
            library.resolve(_recipe_arg(call)),
            language=call.data.get(ATTR_LANGUAGE),
        )
        library.async_update_entities()
        return detail

    async def start_recipe(call: ServiceCall) -> dict[str, Any]:
        entry = _entry_for_call(hass, call)
        runtime = _runtime(hass)[entry.entry_id]
        library = runtime[DATA_RECIPES]
        client = runtime[DATA_CLIENT]
        if client.model != MODEL_CD1:
            raise HomeAssistantError(
                "Cloud recipes are only supported on chunmi.cooker.normalcd1"
            )
        recipe = library.resolve(_recipe_arg(call))
        code = recipe.get("runnable_cookcode")
        if not code:
            raise HomeAssistantError("Recipe has no cookcode")
        await hass.async_add_executor_job(client.start_cookcode, code)
        runtime[DATA_ACTIVE_RECIPE_ID] = int(recipe["id"])
        await runtime[DATA_COORDINATOR].async_refresh_after_command()
        return {"id": int(recipe["id"]), "name": library.summary(recipe)["name"]}

    async def add_favorite(call: ServiceCall) -> None:
        library = _library(hass, call)
        await library.async_set_favorite(
            int(library.resolve(_recipe_arg(call))["id"]), True
        )

    async def remove_favorite(call: ServiceCall) -> None:
        library = _library(hass, call)
        await library.async_set_favorite(
            int(library.resolve(_recipe_arg(call))["id"]), False
        )

    async def list_favorites(call: ServiceCall) -> dict[str, Any]:
        library = _library(hass, call)
        return {
            "recipes": [
                library.summary(library._by_id[recipe_id])
                for recipe_id in sorted(library.favorites)
                if recipe_id in library._by_id
            ]
        }

    async def refresh_recipes(call: ServiceCall) -> dict[str, Any]:
        library = _library(hass, call)
        count = await library.async_refresh()
        return {
            "count": count,
            "last_refresh": library.last_refresh,
            "error": library.last_error,
            "translation_warning": library.translation_warning,
        }

    async def set_recipe_language(call: ServiceCall) -> dict[str, Any]:
        library = _library(hass, call)
        mode = call.data.get(ATTR_LANGUAGE, "ha")
        library.language_mode = mode
        library.async_update_entities()

    async def translate_recipe(call: ServiceCall) -> dict[str, Any]:
        library = _library(hass, call)
        recipe = library.resolve(_recipe_arg(call))
        stats = await library.async_translate_recipe(recipe)
        return {
            "id": int(recipe["id"]),
            "name": library.summary(recipe)["name"],
            "translated": int(stats.get("translated", 0)),
            "failed": int(stats.get("failed", 0)),
            "error": stats.get("error"),
        }

    handlers = {
        SERVICE_START: start,
        SERVICE_STOP: stop,
        SERVICE_RAW_COMMAND: raw_command,
        SERVICE_DUMP: dump,
        SERVICE_SET_MENU: set_menu,
        SERVICE_SET_SETTINGS: set_settings,
        SERVICE_SET_TIMEOUTS: set_timeouts,
        SERVICE_GET_TEMPERATURE_HISTORY: get_temperature_history,
        SERVICE_SEARCH_RECIPES: search_recipes,
        SERVICE_GET_RECIPE: get_recipe,
        SERVICE_START_RECIPE: start_recipe,
        SERVICE_TRANSLATE_RECIPE: translate_recipe,
        SERVICE_ADD_FAVORITE: add_favorite,
        SERVICE_REMOVE_FAVORITE: remove_favorite,
        SERVICE_LIST_FAVORITES: list_favorites,
        SERVICE_REFRESH_RECIPES: refresh_recipes,
        SERVICE_SET_RECIPE_LANGUAGE: set_recipe_language,
    }
    response_services = {
        SERVICE_DUMP,
        SERVICE_GET_TEMPERATURE_HISTORY,
        SERVICE_SEARCH_RECIPES,
        SERVICE_GET_RECIPE,
        SERVICE_START_RECIPE,
        SERVICE_LIST_FAVORITES,
        SERVICE_REFRESH_RECIPES,
        SERVICE_TRANSLATE_RECIPE,
    }
    for name, handler in handlers.items():
        hass.services.async_register(
            DOMAIN,
            name,
            handler,
            schema=SERVICE_SCHEMAS[name],
            supports_response=(
                SupportsResponse.OPTIONAL
                if name in response_services
                else SupportsResponse.NONE
            ),
        )


@callback
def _async_remove_services(hass: HomeAssistant) -> None:
    for name in (
        SERVICE_START,
        SERVICE_STOP,
        SERVICE_RAW_COMMAND,
        SERVICE_DUMP,
        SERVICE_SET_MENU,
        SERVICE_SET_SETTINGS,
        SERVICE_SET_TIMEOUTS,
        SERVICE_GET_TEMPERATURE_HISTORY,
        SERVICE_SEARCH_RECIPES,
        SERVICE_GET_RECIPE,
        SERVICE_START_RECIPE,
        SERVICE_ADD_FAVORITE,
        SERVICE_REMOVE_FAVORITE,
        SERVICE_LIST_FAVORITES,
        SERVICE_REFRESH_RECIPES,
        SERVICE_SET_RECIPE_LANGUAGE,
    ):
        hass.services.async_remove(DOMAIN, name)
