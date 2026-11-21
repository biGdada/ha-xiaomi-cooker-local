"""Action buttons for the cooker."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DATA_ACTIVE_RECIPE_ID,
    DATA_CLIENT,
    DATA_COORDINATOR,
    DATA_RECIPES,
    DATA_SELECTED_PROFILE,
    DOMAIN,
    MODEL_CD1,
)
from .entity import CookerEntity
from .profiles import profiles_for_model, resolve_profile


@dataclass(frozen=True, kw_only=True)
class CookerButtonDescription(ButtonEntityDescription):
    """Button description with the client method to call."""

    action: str = ""


CD1_BUTTONS: tuple[CookerButtonDescription, ...] = (
    CookerButtonDescription(
        key="start_cooking", name="Start cooking", icon="mdi:play", action="start"
    ),
    CookerButtonDescription(
        key="stop_cooking", name="Stop cooking", icon="mdi:stop", action="stop"
    ),
    CookerButtonDescription(
        key="refresh", name="Refresh state", icon="mdi:refresh", action="refresh"
    ),
    CookerButtonDescription(
        key="refresh_recipes",
        name="Refresh recipes",
        icon="mdi:download",
        action="refresh_recipes",
    ),
)

BUTTONS: tuple[CookerButtonDescription, ...] = (
    CookerButtonDescription(
        key="start_cooking", name="Start cooking", icon="mdi:play", action="start"
    ),
    CookerButtonDescription(
        key="stop_cooking", name="Stop cooking", icon="mdi:stop", action="stop"
    ),
    CookerButtonDescription(
        key="stop_legacy", name="Stop (legacy command)", icon="mdi:stop-circle-outline",
        action="stop_legacy",
    ),
    CookerButtonDescription(
        key="acknowledge", name="Acknowledge warnings", icon="mdi:check",
        action="set_acknowledge",
    ),
    CookerButtonDescription(
        key="no_warnings", name="Disable warnings", icon="mdi:bell-off",
        action="set_no_warnings",
    ),
    CookerButtonDescription(
        key="refresh", name="Refresh state", icon="mdi:refresh", action="refresh"
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    buttons = (
        CD1_BUTTONS if entry.data.get("model") == MODEL_CD1 else BUTTONS
    )
    async_add_entities(CookerButton(coordinator, entry, desc) for desc in buttons)


class CookerButton(CookerEntity, ButtonEntity):
    """Button that invokes one cooker command."""

    entity_description: CookerButtonDescription

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        action = self.entity_description.action
        parsed = self.status.parsed if self.status else {}
        is_idle = parsed.get("status_code") == 1
        if action == "start":
            return is_idle
        if action in ("stop", "stop_legacy"):
            return not is_idle
        return True

    async def async_press(self) -> None:
        action = self.entity_description.action
        runtime = self.hass.data[DOMAIN][self._entry.entry_id]
        client = runtime[DATA_CLIENT]

        if action == "refresh":
            await self.coordinator.async_request_refresh()
            return

        if action == "refresh_recipes":
            library = runtime[DATA_RECIPES]
            await library.async_refresh()
            self.async_write_ha_state()
            return

        if action == "start":
            runtime[DATA_ACTIVE_RECIPE_ID] = None
            model = self._entry.data.get("model")
            selected = runtime.get(DATA_SELECTED_PROFILE)
            if model == MODEL_CD1:
                # cd1 uses small integer cook modes, not classic hex profiles.
                profile = selected or "Quick Cook"
            else:
                if not selected:
                    available = profiles_for_model(model)
                    selected = available[0]["profile"] if available else None
                if not selected:
                    raise RuntimeError("No cooking profile available for this model")
                profile = resolve_profile(
                    model, selected, self._entry.options.get("profiles")
                )
            await self.hass.async_add_executor_job(client.start, profile)
        else:
            if action in ("stop", "stop_legacy"):
                runtime[DATA_ACTIVE_RECIPE_ID] = None
            await self.hass.async_add_executor_job(getattr(client, action))

        await self.coordinator.async_refresh_after_command()
