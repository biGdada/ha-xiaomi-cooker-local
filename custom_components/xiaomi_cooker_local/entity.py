"""Shared entity base class."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import CookerDataUpdateCoordinator
from .parsing import CookerStatus


class CookerEntity(CoordinatorEntity[CookerDataUpdateCoordinator]):
    """Base class for all cooker entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CookerDataUpdateCoordinator,
        entry: ConfigEntry,
        description: EntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

    @property
    def status(self) -> CookerStatus:
        """Return the latest parsed snapshot."""
        return self.coordinator.data

    @property
    def device_info(self) -> DeviceInfo:
        model = self.coordinator.client.model or self._entry.data.get("model")
        info = DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.data.get("name") or "Rice Cooker",
            manufacturer=MANUFACTURER,
            model=model or "Unknown cooker",
        )
        version = self.status.parsed.get("firmware_label") if self.status else None
        if version:
            info["sw_version"] = str(version)
        return info
