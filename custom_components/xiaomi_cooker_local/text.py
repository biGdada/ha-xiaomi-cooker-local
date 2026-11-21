"""Native text entity holding the recipe search query."""

from __future__ import annotations

from homeassistant.components.text import (
    TextEntity,
    TextEntityDescription,
    TextMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_RECIPE_QUERY, DOMAIN, MANUFACTURER, MODEL_CD1

DESCRIPTION = TextEntityDescription(
    key="recipe_query",
    name="Recipe search query",
    icon="mdi:magnify",
    mode=TextMode.TEXT,
    native_max=255,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if entry.data.get("model") == MODEL_CD1:
        async_add_entities([RecipeQueryText(entry)])


class RecipeQueryText(TextEntity):
    """Search term used by the Search recipes action."""

    _attr_has_entity_name = True
    entity_description = DESCRIPTION

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_recipe_query"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("name") or "Rice Cooker",
            manufacturer=MANUFACTURER,
            model=entry.data.get("model") or "Unknown cooker",
        )

    @property
    def native_value(self) -> str:
        return str(
            self.hass.data[DOMAIN][self._entry.entry_id].get(DATA_RECIPE_QUERY) or ""
        )

    async def async_set_value(self, value: str) -> None:
        self.hass.data[DOMAIN][self._entry.entry_id][DATA_RECIPE_QUERY] = value.strip()
        self.async_write_ha_state()
