"""Diagnostics support (redacts the device token)."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import CONF_TOKEN, DATA_CLIENT, DATA_COORDINATOR, DOMAIN

REDACTED = "**REDACTED**"


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    runtime = hass.data[DOMAIN][entry.entry_id]
    client = runtime[DATA_CLIENT]
    coordinator = runtime[DATA_COORDINATOR]

    device = dr.async_get(hass).async_get_device(
        identifiers={(DOMAIN, entry.entry_id)}
    )
    return {
        "config": {
            key: (REDACTED if key == CONF_TOKEN else value)
            for key, value in {**entry.data, **entry.options}.items()
        },
        "device": device.as_dict() if device else None,
        "model": client.model,
        "info": await hass.async_add_executor_job(client.info),
        "raw_status": await hass.async_add_executor_job(client.raw_status),
        "parsed_status": coordinator.data.parsed if coordinator.data else None,
    }
