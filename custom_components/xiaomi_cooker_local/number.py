"""Cooker interaction timeout settings."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_CLIENT, DATA_COORDINATOR, DOMAIN, MODEL_CD1
from .entity import CookerEntity
from .parsing import TIMEOUT_FIELDS

NUMBERS: tuple[NumberEntityDescription, ...] = tuple(
    NumberEntityDescription(
        key=name,
        name=name.replace("_", " ").title(),
        native_min_value=0,
        native_max_value=255,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        icon="mdi:timer-cog",
    )
    for name in TIMEOUT_FIELDS
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if entry.data.get("model") == MODEL_CD1:
        return
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    async_add_entities(CookerNumber(coordinator, entry, desc) for desc in NUMBERS)


class CookerNumber(CookerEntity, NumberEntity):
    """One timeout byte from the ``delay`` field."""

    @property
    def native_value(self) -> float | None:
        return self.status.parsed["timeouts"].get(self.entity_description.key)

    async def async_set_native_value(self, value: float) -> None:
        client = self.hass.data[DOMAIN][self._entry.entry_id][DATA_CLIENT]
        await self.hass.async_add_executor_job(
            client.update_timeouts, {self.entity_description.key: int(value)}
        )
        await self.coordinator.async_request_refresh()
