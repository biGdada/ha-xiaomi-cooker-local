"""Synchronous miIO client wrapper for chunmi.cooker.* devices.

All methods are intentionally blocking: call them through
``hass.async_add_executor_job`` from Home Assistant.
"""

from __future__ import annotations

import logging
from typing import Any

from miio import Device
from miio.exceptions import DeviceException

from .const import MODEL_CD1, STATUS_FIELDS
from .parsing import (
    CD1_COOK_MODES,
    CD1_STATUS_NAMES,
    CookerStatus,
    parse_status,
    parse_temperature_history,
    update_settings_hex,
    update_timeouts_hex,
)

_LOGGER = logging.getLogger(__name__)

CD1_PROPERTY_NAMES: tuple[str, ...] = (
    "status",
    "cook_mode",
    "temp",
    "menu",
    "version",
    "t_cook",
)


class CookerClient:
    """Thin, tolerant wrapper around python-miio's transport."""

    def __init__(
        self,
        host: str,
        token: str,
        model: str | None = None,
        timeout: int = 5,
    ) -> None:
        self.host = host
        self.token = token
        self.model = model
        self.timeout = timeout
        self._device: Device | None = None

    def connect(self) -> Device:
        if self._device is None:
            self._device = Device(
                self.host,
                self.token,
                timeout=self.timeout,
                model=self.model,
                lazy_discover=True,
            )
        return self._device

    def close(self) -> None:
        device = self._device
        self._device = None
        if device is not None:
            close = getattr(device, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # pragma: no cover - best effort cleanup
                    _LOGGER.debug("Failed to close miio device", exc_info=True)

    @staticmethod
    def _info_dict(info: Any) -> dict[str, Any]:
        if info is None:
            return {}
        if isinstance(info, dict):
            return dict(info)
        result: dict[str, Any] = {}
        for name in (
            "model",
            "device_id",
            "mac_address",
            "hardware_version",
            "firmware_version",
            "local_ip",
        ):
            value = getattr(info, name, None)
            if value is not None:
                result[name] = value
        if not result:
            result["raw"] = str(info)
        return result

    def info(self) -> dict[str, Any]:
        """Return device info and auto-detected model."""
        return self._info_dict(self.connect().info())

    def probe(self) -> dict[str, Any]:
        """Validate credentials and return info + one raw status sample."""
        device = self.connect()
        info = self._info_dict(device.info())
        values = self._raw_values(device)
        if not self.model:
            self.model = info.get("model") or None
        return {**info, "raw_status": values}

    def _raw_values(self, device: Device | None = None) -> list[Any]:
        device = device or self.connect()
        response = device.send("get_prop", ["all"])
        if isinstance(response, (list, tuple)):
            return list(response)
        raise DeviceException(f"Unexpected get_prop response: {response!r}")

    def named_values(self) -> dict[str, Any]:
        """Read cd1's supported named properties (one request per property)."""
        device = self.connect()
        result: dict[str, Any] = {}
        for name in CD1_PROPERTY_NAMES:
            try:
                values = device.send("get_prop", [name])
            except Exception:  # pragma: no cover - a property may be unsupported
                _LOGGER.debug("Cooker property %s unavailable", name, exc_info=True)
                continue
            if isinstance(values, (list, tuple)) and values:
                result[name] = values[0]
        return result

    def status(self) -> CookerStatus:
        """Poll and parse the cooker state."""
        values = self._raw_values()
        status = parse_status(values)
        if self.model == MODEL_CD1:
            named = self.named_values()
            status.raw["named"] = named
            status.parsed["named"] = named
            status_code = named.get("status")
            if status_code is not None:
                status.parsed["status_code"] = status_code
                status.parsed["status_name"] = CD1_STATUS_NAMES.get(
                    status_code, "Unknown"
                )
                status.parsed["mode_name"] = status.parsed["status_name"]
                status.parsed["cooking"] = status_code == 2
            cook_mode = named.get("cook_mode")
            if cook_mode is not None:
                status.parsed["cook_mode_code"] = cook_mode
                status.parsed["cook_mode_name"] = CD1_COOK_MODES.get(
                    cook_mode, "Unknown"
                )
            if named.get("temp") is not None:
                status.parsed["temperature"] = named["temp"]
            if named.get("t_cook") is not None:
                status.parsed["remaining"] = named["t_cook"]
            if named.get("menu") is not None:
                status.parsed["menu_raw"] = named["menu"]
            if named.get("version") is not None:
                status.parsed["version_raw"] = named["version"]
        return status

    def raw_status(self) -> dict[str, Any]:
        """Return raw fields with their known names (for mapping/debugging)."""
        values = self._raw_values()
        return {
            **{
                name: values[index] if index < len(values) else None
                for index, name in enumerate(STATUS_FIELDS)
            },
            **{
                f"raw_{index}": value
                for index, value in enumerate(values)
                if index >= len(STATUS_FIELDS)
            },
            "_values": values,
        }

    def raw_command(self, method: str, parameters: Any = None) -> Any:
        """Send any miIO command (used for protocol mapping)."""
        return self.connect().send(method, parameters)

    @staticmethod
    def cd1_mode(profile: str | int | None) -> int:
        """Translate a profile label into a cd1 cook-mode code (defaults 2)."""
        if profile is None:
            return 2
        text = str(profile).strip()
        if text.isdigit():
            code = int(text)
            if code in CD1_COOK_MODES:
                return code
        for code, name in CD1_COOK_MODES.items():
            if name.lower() == text.lower():
                return code
        return 2

    def start_cook(self, mode: int | str | None = None) -> Any:
        """Start cooking with a cd1 mode code (confirmed working locally)."""
        code = self.cd1_mode(mode)
        _LOGGER.info("Starting cd1 cook mode %s (%s)", code, CD1_COOK_MODES[code])
        return self.raw_command("start_cook", [code])

    def start(self, profile: str) -> Any:
        if self.model == MODEL_CD1:
            return self.start_cook(profile)
        return self.raw_command("set_start", [profile])

    def start_cookcode(self, cookcode: str) -> Any:
        """Start a full 133-byte recipe profile via the local ``set_start`` RPC.

        The cookcode must already have been rewritten for the temporary slot
        (see ``recipes.make_runnable``); cloud codes are rejected locally.
        """
        if len(cookcode) != 266:
            raise ValueError(f"Expected a 266-character cookcode, got {len(cookcode)}")
        return self.raw_command("set_start", [cookcode])

    def cancel_cooking(self) -> Any:
        """Cancel cooking on cd1 firmware (confirmed working locally)."""
        return self.raw_command("cancel_cooking", [])

    def stop(self) -> Any:
        if self.model == MODEL_CD1:
            return self.cancel_cooking()
        return self.raw_command("set_func", ["end02"])

    def stop_legacy(self) -> Any:
        return self.raw_command("set_func", ["end"])

    def set_no_warnings(self) -> Any:
        return self.raw_command("set_func", ["nowarn"])

    def set_acknowledge(self) -> Any:
        return self.raw_command("set_func", ["ack"])

    def set_menu(self, profile: str) -> Any:
        return self.raw_command("set_menu", [profile])

    def set_interaction(
        self,
        settings_hex: str,
        led_off: int,
        lid_open: int,
        lid_open_warning: int,
    ) -> Any:
        return self.raw_command(
            "set_interaction",
            [
                settings_hex,
                f"{led_off:x}",
                f"{lid_open:x}",
                f"{lid_open_warning:x}",
            ],
        )

    def update_flags(self, updates: dict[str, bool]) -> Any:
        """Apply multiple setting bit changes in one device round-trip."""
        status = self.status()
        new_settings = update_settings_hex(status.raw.get("setting"), updates)
        timeouts = status.parsed["timeouts"]
        return self.set_interaction(
            new_settings,
            timeouts["led_off"],
            timeouts["lid_open"],
            timeouts["lid_open_warning"],
        )

    def update_flag(self, flag: str, enabled: bool) -> Any:
        return self.update_flags({flag: enabled})

    def update_timeouts(self, updates: dict[str, int]) -> Any:
        status = self.status()
        new_timeouts = update_timeouts_hex(status.raw.get("delay"), updates)
        return self.set_interaction(
            status.parsed["settings_raw"],
            int(new_timeouts[0:2], 16),
            int(new_timeouts[2:4], 16),
            int(new_timeouts[4:6], 16),
        )

    def temperature_history(self) -> list[int]:
        response = self.raw_command("get_temp_history")
        if isinstance(response, (list, tuple)) and response:
            return parse_temperature_history(response[0])
        if isinstance(response, str):
            return parse_temperature_history(response)
        return []
