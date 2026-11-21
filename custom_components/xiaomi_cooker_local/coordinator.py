"""Data update coordinator for the cooker."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from miio.exceptions import DeviceException

from .client import CookerClient
from .parsing import CookerStatus

_LOGGER = logging.getLogger(__name__)


class CookerDataUpdateCoordinator(DataUpdateCoordinator[CookerStatus]):
    """Poll the cooker and expose a parsed snapshot to entities."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        client: CookerClient,
        name: str,
        update_interval: timedelta,
        config_entry: ConfigEntry,
    ) -> None:
        super().__init__(
            hass=hass,
            logger=_LOGGER,
            name=name,
            update_interval=update_interval,
            config_entry=config_entry,
        )
        self.client = client
        self.device_info: dict[str, Any] = {}

    async def _async_update_data(self) -> CookerStatus:
        try:
            data = await self.hass.async_add_executor_job(self.client.status)
        except (DeviceException, OSError, ValueError, TypeError) as err:
            raise UpdateFailed(f"Error communicating with cooker: {err}") from err
        if not self.client.model:
            try:
                self.client.model = (
                    await self.hass.async_add_executor_job(self.client.info)
                ).get("model")
            except Exception:  # pragma: no cover - model is cosmetic here
                _LOGGER.debug("Could not determine cooker model", exc_info=True)
        return data

    async def async_refresh_after_command(self) -> None:
        """Refresh now and again shortly after a state-changing command.

        The cooker acknowledges commands before its reported status changes,
        so an immediate refresh alone can show the previous state.
        """
        await self.async_request_refresh()

        @callback
        def _refresh_again(_now: datetime) -> None:
            self.hass.async_create_task(self.async_request_refresh())

        async_call_later(self.hass, 2, _refresh_again)
        async_call_later(self.hass, 5, _refresh_again)
