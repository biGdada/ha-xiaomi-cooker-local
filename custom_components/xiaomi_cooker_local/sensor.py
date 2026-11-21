"""Sensors exposing every decoded cooker data point."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DATA_ACTIVE_RECIPE_ID,
    DATA_COORDINATOR,
    DATA_RECIPES,
    DOMAIN,
    MANUFACTURER,
)
from .entity import CookerEntity

SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="status_name", name="Cooker status", icon="mdi:state-machine"
    ),
    SensorEntityDescription(
        key="cook_mode_name", name="Current cook mode", icon="mdi:rice"
    ),
    SensorEntityDescription(
        key="timer_seconds",
        name="Timer remaining",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        icon="mdi:timer",
    ),
    SensorEntityDescription(
        key="cook_minutes",
        name="Cook duration",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        icon="mdi:timer-outline",
    ),
    SensorEntityDescription(
        key="reservation_seconds",
        name="Reservation",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        icon="mdi:clock-start",
    ),
    SensorEntityDescription(
        key="profile_id", name="Profile ID", icon="mdi:identifier"
    ),
    SensorEntityDescription(
        key="stage_code", name="Stage code", icon="mdi:numeric"
    ),
    SensorEntityDescription(
        key="run_marker", name="Run marker", icon="mdi:numeric"
    ),
    SensorEntityDescription(
        key="device_clock", name="Device clock", icon="mdi:clock-outline"
    ),
    SensorEntityDescription(
        key="last_cook_start", name="Last cook started", icon="mdi:play"
    ),
    SensorEntityDescription(
        key="last_cook_end", name="Last cook finished", icon="mdi:stop"
    ),
    SensorEntityDescription(key="mode_name", name="Mode", icon="mdi:state-machine"),
    SensorEntityDescription(
        key="mode", name="Mode code", icon="mdi:identifier",
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(key="menu", name="Menu", icon="mdi:rice"),
    SensorEntityDescription(
        key="menu_raw", name="Menu raw", icon="mdi:identifier",
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="stage_name", name="Stage", icon="mdi:format-list-bulleted"
    ),
    SensorEntityDescription(
        key="stage_description", name="Stage description", icon="mdi:text"
    ),
    SensorEntityDescription(
        key="stage_state", name="Stage code", icon="mdi:numeric",
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="stage_raw", name="Stage raw", icon="mdi:identifier",
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(key="rice_id", name="Rice ID", icon="mdi:grain"),
    SensorEntityDescription(key="taste", name="Taste", icon="mdi:food"),
    SensorEntityDescription(key="taste_phase", name="Taste phase", icon="mdi:food"),
    SensorEntityDescription(
        key="temperature",
        name="Temperature",
        native_unit_of_measurement="°C",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
    ),
    SensorEntityDescription(
        key="temp_raw", name="Temperature raw", icon="mdi:identifier",
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="start_time", name="Start time", icon="mdi:clock-start"
    ),
    SensorEntityDescription(
        key="remaining",
        name="Remaining",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        icon="mdi:timer",
    ),
    SensorEntityDescription(
        key="cooking_delayed",
        name="Delayed start",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        icon="mdi:timer-sand",
    ),
    SensorEntityDescription(
        key="duration",
        name="Duration",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        icon="mdi:timer-outline",
    ),
    SensorEntityDescription(
        key="favorite", name="Favorite menu", icon="mdi:star"
    ),
    SensorEntityDescription(
        key="favorite_raw", name="Favorite raw", icon="mdi:identifier",
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="hardware_label", name="Hardware version", icon="mdi:chip"
    ),
    SensorEntityDescription(
        key="firmware_label", name="Firmware version", icon="mdi:chip"
    ),
    SensorEntityDescription(
        key="version_raw", name="Version raw", icon="mdi:identifier",
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="settings_raw", name="Settings raw", icon="mdi:identifier",
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="timeouts_raw", name="Timeouts raw", icon="mdi:identifier",
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="custom_raw", name="Custom raw", icon="mdi:identifier",
        entity_registry_enabled_default=False,
    ),
    *(
        SensorEntityDescription(
            key=appointment,
            name=appointment.replace("_", " ").title(),
            icon="mdi:clock-outline",
        )
        for appointment in (
            "jingzhu_appointment",
            "kuaizhu_appointment",
            "zhuzhou_appointment",
            "favorite_appointment",
            "favorite_cooking",
        )
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    entities: list[SensorEntity] = [
        CookerSensor(coordinator, entry, desc) for desc in SENSORS
    ]
    entities.extend(
        [
            CurrentActionSensor(coordinator, entry),
            RecipeIdSensor(coordinator, entry),
        ]
    )
    if entry.data.get("model") == "chunmi.cooker.normalcd1":
        entities.extend(
            [
                RecipeLibrarySensor(entry),
                RecipeTranslationSensor(entry),
                RecipeRefreshSensor(entry),
            ]
        )
    async_add_entities(entities)


class CookerSensor(CookerEntity, SensorEntity):
    """A decoded cooker value."""

    @property
    def native_value(self) -> Any:
        return self.status.parsed.get(self.entity_description.key)


class CurrentActionSensor(CookerEntity, SensorEntity):
    """Human-readable action: recipe name, mode, external recipe, or Off."""

    _attr_name = "Current action"
    _attr_icon = "mdi:pot-steam"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            SensorEntityDescription(key="current_action"),
        )

    @property
    def native_value(self) -> str:
        status = self.status
        parsed = status.parsed if status else {}
        status_code = parsed.get("status_code")
        if status_code == 1:
            return "Off"

        runtime = self.hass.data[DOMAIN][self._entry.entry_id]
        active_recipe_id = runtime.get(DATA_ACTIVE_RECIPE_ID)
        library = runtime.get(DATA_RECIPES)
        if active_recipe_id and library and hasattr(library, "_by_id"):
            recipe = library._by_id.get(int(active_recipe_id))
            if recipe:
                return str(library.summary(recipe).get("name") or "External Recipe")

        mode_name = parsed.get("cook_mode_name")
        if mode_name and mode_name not in ("Unknown", "—"):
            # Built-in mode cooking when no known integration recipe is active.
            if active_recipe_id is None:
                return str(mode_name)

        if parsed.get("cooking") or status_code not in (1, None):
            return "External Recipe"
        return "Off"


class RecipeIdSensor(CookerEntity, SensorEntity):
    """Active recipe id, unknown for external app recipe, blank when off/built-in."""

    _attr_name = "Recipe ID"
    _attr_icon = "mdi:identifier"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            SensorEntityDescription(key="active_recipe_id"),
        )

    @property
    def native_value(self) -> str | int | None:
        status = self.status
        parsed = status.parsed if status else {}
        status_code = parsed.get("status_code")
        if status_code == 1:
            return ""
        runtime = self.hass.data[DOMAIN][self._entry.entry_id]
        active_recipe_id = runtime.get(DATA_ACTIVE_RECIPE_ID)
        if active_recipe_id:
            return int(active_recipe_id)
        if parsed.get("cooking") or status_code not in (1, None):
            return "unknown"
        return ""


class RecipeLibrarySensor(SensorEntity):
    """Expose the recipe catalogue, favorites and last viewed recipe."""

    _attr_has_entity_name = True
    _attr_name = "Recipe library"
    _attr_icon = "mdi:book-open-variant"

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_recipe_library"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("name") or "Rice Cooker",
            manufacturer=MANUFACTURER,
            model=entry.data.get("model") or "Unknown cooker",
        )

    @property
    def _library(self):
        return self.hass.data[DOMAIN][self._entry.entry_id][DATA_RECIPES]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._library.add_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        self._library.remove_listener(self.async_write_ha_state)
        await super().async_will_remove_from_hass()

    @property
    def native_value(self) -> int:
        return len(self._library.recipes)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        library = self._library
        return {
            "language": library.display_language,
            "language_label": library.language_label,
            "source": library.source,
            "last_refresh": library.last_refresh,
            "last_error": library.last_error,
            "favorite_count": len(library.favorites),
            "favorites": [
                library.summary(library._by_id[recipe_id])
                for recipe_id in sorted(library.favorites)
                if recipe_id in library._by_id
            ],
            "last_query": library.last_query,
            "last_search": library.last_search,
            "last_recipe": library.last_recipe,
            "translation_warning": library.translation_warning,
        }


class RecipeTranslationSensor(SensorEntity):
    """Show translation service problems from the last recipe refresh."""

    _attr_has_entity_name = True
    _attr_name = "Recipe translation status"
    _attr_icon = "mdi:translate"

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_recipe_translation_status"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("name") or "Rice Cooker",
            manufacturer=MANUFACTURER,
            model=entry.data.get("model") or "Unknown cooker",
        )

    @property
    def _library(self):
        return self.hass.data[DOMAIN][self._entry.entry_id][DATA_RECIPES]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._library.add_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        self._library.remove_listener(self.async_write_ha_state)
        await super().async_will_remove_from_hass()

    @property
    def native_value(self) -> str:
        return self._library.translation_warning or "OK"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "failed_strings": self._library.translation_failures,
            "last_refresh": self._library.last_refresh,
        }


class RecipeRefreshSensor(SensorEntity):
    """Shared recipe-refresh state so every card sees the same progress."""

    _attr_has_entity_name = True
    _attr_name = "Recipe refresh status"
    _attr_icon = "mdi:sync"

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_recipe_refresh_status"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("name") or "Rice Cooker",
            manufacturer=MANUFACTURER,
            model=entry.data.get("model") or "Unknown cooker",
        )

    @property
    def _library(self):
        return self.hass.data[DOMAIN][self._entry.entry_id][DATA_RECIPES]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._library.add_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        self._library.remove_listener(self.async_write_ha_state)
        await super().async_will_remove_from_hass()

    @property
    def native_value(self) -> str:
        return self._library.refresh_phase

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        library = self._library
        total = library.refresh_total
        done = library.refresh_done
        return {
            "in_progress": library.refresh_phase not in ("idle", "done"),
            "phase": library.refresh_phase,
            "done": done,
            "total": total,
            "percent": min(100, round(done / total * 100)) if total else 0,
        }
