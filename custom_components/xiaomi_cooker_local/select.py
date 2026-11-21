"""Select the cooking profile to use for the start button/service."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DATA_COORDINATOR,
    DATA_SELECTED_PROFILE,
    DOMAIN,
    MODEL_CD1,
)
from .entity import CookerEntity
from .parsing import CD1_COOK_MODES
from .profiles import profile_titles

DESCRIPTION = SelectEntityDescription(
    key="profile",
    name="Cooking profile",
    icon="mdi:rice",
)

CD1_DESCRIPTION = SelectEntityDescription(
    key="cook_mode",
    name="Cook mode",
    icon="mdi:rice",
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    if entry.data.get("model") == MODEL_CD1:
        async_add_entities([CookerModeSelect(coordinator, entry)])
        return
    async_add_entities([CookerProfileSelect(coordinator, entry)])


class CookerProfileSelect(CookerEntity, SelectEntity):
    """Remembers which profile the start action should use."""

    entity_description = DESCRIPTION

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, self.entity_description)

    @property
    def options(self) -> list[str]:
        return profile_titles(
            self._entry.data.get("model"), self._entry.options.get("profiles")
        )

    @property
    def current_option(self) -> str | None:
        selected = self.hass.data[DOMAIN][self._entry.entry_id].get(
            DATA_SELECTED_PROFILE
        )
        if selected in self.options:
            return selected
        return None

    async def async_select_option(self, option: str) -> None:
        if option not in self.options:
            raise ValueError(f"Unknown cooking profile: {option}")
        self.hass.data[DOMAIN][self._entry.entry_id][DATA_SELECTED_PROFILE] = option
        self.async_write_ha_state()


class CookerModeSelect(CookerEntity, SelectEntity):
    """Selects the cd1 cook mode used by the start action."""

    entity_description = CD1_DESCRIPTION

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, self.entity_description)

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        parsed = self.status.parsed if self.status else {}
        return parsed.get("status_code") == 1

    @property
    def options(self) -> list[str]:
        return list(CD1_COOK_MODES.values())

    @property
    def current_option(self) -> str | None:
        parsed = self.status.parsed if self.status else {}
        reported = parsed.get("cook_mode_name")
        selected = self.hass.data[DOMAIN][self._entry.entry_id].get(
            DATA_SELECTED_PROFILE
        )
        is_idle = parsed.get("status_code") == 1
        if is_idle:
            if selected in self.options:
                return selected
            if reported in self.options:
                return reported
            return None
        if reported in self.options:
            return reported
        if selected in self.options:
            return selected
        return None

    async def async_select_option(self, option: str) -> None:
        if option not in self.options:
            raise ValueError(f"Unknown cook mode: {option}")
        self.hass.data[DOMAIN][self._entry.entry_id][DATA_SELECTED_PROFILE] = option
        self.async_write_ha_state()
