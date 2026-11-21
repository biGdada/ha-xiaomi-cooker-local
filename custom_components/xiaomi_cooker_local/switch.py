"""Writable cooker settings exposed as switches."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_CLIENT, DATA_COORDINATOR, DOMAIN, MODEL_CD1
from .entity import CookerEntity
from .parsing import WRITABLE_SETTINGS

SWITCHES: tuple[SwitchEntityDescription, ...] = tuple(
    SwitchEntityDescription(
        key=name,
        name=name.replace("_", " ").title(),
        icon="mdi:toggle-switch",
    )
    for name in WRITABLE_SETTINGS
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if entry.data.get("model") == MODEL_CD1:
        return
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    async_add_entities(
        CookerSettingSwitch(coordinator, entry, desc) for desc in SWITCHES
    )


class CookerSettingSwitch(CookerEntity, SwitchEntity):
    """A bit in the cooker's setting mask."""

    @property
    def is_on(self) -> bool:
        return bool(self.status.parsed.get(f"flag_{self.entity_description.key}"))

    async def _async_set(self, value: bool) -> None:
        client = self.hass.data[DOMAIN][self._entry.entry_id][DATA_CLIENT]
        await self.hass.async_add_executor_job(
            client.update_flag, self.entity_description.key, value
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs) -> None:
        await self._async_set(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._async_set(False)
