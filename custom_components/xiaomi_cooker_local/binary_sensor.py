"""Read-only boolean state from the cooker."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_COORDINATOR, DOMAIN
from .entity import CookerEntity

BINARY_SENSORS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key="cooking",
        name="Cooking",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:stove",
    ),
    BinarySensorEntityDescription(
        key="flag_pressure_supported",
        name="Pressure supported",
        icon="mdi:pressure",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    async_add_entities(
        CookerBinarySensor(coordinator, entry, desc) for desc in BINARY_SENSORS
    )


class CookerBinarySensor(CookerEntity, BinarySensorEntity):
    """A boolean cooker state."""

    @property
    def is_on(self) -> bool | None:
        value = self.status.parsed.get(self.entity_description.key)
        return None if value is None else bool(value)
