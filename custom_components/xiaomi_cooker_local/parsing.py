"""Tolerant parsing of the raw miIO cooker payloads.

python-miio's ``CookerStatus`` raises on unknown ``func`` values (new firmware
often adds modes).  We deliberately keep a *raw* representation of everything
and parse known fields defensively, so an unknown mode never breaks polling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any

from .const import STATUS_FIELDS

MODE_NAMES: dict[str, str] = {
    "waiting": "Idle",
    "running": "Cooking",
    "precook": "Delayed start",
    "autokeepwarm": "Keep warm",
    "cooking": "Cooking",
    "finish": "Finished",
    "finisha": "Finished",
    "keepwarm": "Keep warm",
    "keep_temp": "Keep temperature",
    "notice": "Notice",
    "offline": "Offline",
    "online": "Online",
    "start": "Starting",
    "startp": "Starting",
    "resume": "Resuming",
    "resumep": "Resuming",
    "cancel": "Cancelled",
    "отмена": "Cancelled",
}

CD1_STATUS_NAMES: dict[int, str] = {
    1: "Idle",
    2: "Running",
    3: "Keep Warm",
    4: "Cook Reservation",
}

CD1_COOK_MODES: dict[int, str] = {
    1: "Fine Cook",
    2: "Quick Cook",
    3: "Cook Congee",
    4: "Keep Warm",
}

COOKING_STAGES: dict[int, dict[str, str]] = {
    0: {
        "name": "Quickly preheat",
        "description": (
            "Increase temperature in a controlled manner to soften rice gradually"
        ),
    },
    1: {
        "name": "Water-absorbing",
        "description": "Increase temperature to let the grains absorb water",
    },
    2: {"name": "Boiling", "description": "Last high heating, to cook rice evenly"},
    3: {
        "name": "Gelatinizing",
        "description": (
            "Steaming under high temperature to bring sweetness to the grains"
        ),
    },
    4: {"name": "Braising", "description": "Absorb water at moderate temperature"},
    5: {"name": "Boiling", "description": "Operate at full load to boil rice"},
    7: {"name": "Boiling", "description": "Operate at full load to boil rice"},
    8: {
        "name": "Warm up rice",
        "description": "Cyclic heating for even temperature and texture",
    },
    10: {
        "name": "High temperature gelatinization",
        "description": "High-temperature steam treatment",
    },
    16: {"name": "Cooking finished", "description": ""},
}

SETTING_FLAGS: tuple[tuple[str, int, int], ...] = (
    ("pressure_supported", 0, 0x01),
    ("led_on", 0, 0x02),
    ("auto_keep_warm", 0, 0x04),
    ("lid_open_warning", 0, 0x08),
    ("lid_open_warning_delayed", 0, 0x10),
    ("jingzhu_auto_keep_warm", 1, 0x01),
    ("kuaizhu_auto_keep_warm", 1, 0x02),
    ("zhuzhou_auto_keep_warm", 1, 0x04),
    ("favorite_auto_keep_warm", 1, 0x08),
)

WRITABLE_SETTINGS: tuple[str, ...] = tuple(
    name for name, _, _ in SETTING_FLAGS if name != "pressure_supported"
)

TIMEOUT_FIELDS: tuple[str, ...] = (
    "led_off",
    "lid_open",
    "lid_open_warning",
)

CUSTOM_APPOINTMENTS: tuple[tuple[str, int], ...] = (
    ("jingzhu_appointment", 0),
    ("kuaizhu_appointment", 2),
    ("zhuzhou_appointment", 4),
    ("favorite_appointment", 6),
    ("favorite_cooking", 8),
    ("unknown_10_11", 10),
    ("unknown_12_13", 12),
    ("unknown_14_15", 14),
)


@dataclass(slots=True)
class CookerStatus:
    """Parsed plus untouched raw snapshot of one poll."""

    raw: dict[str, Any] = field(default_factory=dict)
    values: list[Any] = field(default_factory=list)
    parsed: dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, key: str) -> Any:
        return self.parsed[key]


def _as_hex(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, int):
        return f"{value:x}"
    return str(value).strip()


def _hex_int(value: Any, default: int | None = None) -> int | None:
    text = _as_hex(value)
    if not text:
        return default
    try:
        return int(text, 16)
    except ValueError:
        return default


def _int(value: Any, default: int | None = None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_settings(value: Any) -> dict[str, Any]:
    """Decode the two-octet ``setting`` bitmask."""
    raw = _as_hex(value)
    octets = []
    for index in range(0, min(len(raw), 4), 2):
        try:
            octets.append(int(raw[index : index + 2], 16))
        except ValueError:
            octets.append(0)
    while len(octets) < 2:
        octets.append(0)

    flags = {
        name: bool(octets[octet_index] & mask)
        for name, octet_index, mask in SETTING_FLAGS
    }
    return {
        "raw": raw,
        "octets": octets,
        "flags": flags,
        **flags,
    }


def update_settings_hex(value: Any, updates: dict[str, bool]) -> str:
    """Return a new ``setting`` hex string with selected flags changed."""
    settings = parse_settings(value)
    octets = list(settings["octets"])
    for name, octet_index, mask in SETTING_FLAGS:
        if name not in updates:
            continue
        if updates[name]:
            octets[octet_index] |= mask
        else:
            octets[octet_index] &= 0xFF ^ mask
    return "".join(f"{octet:02x}" for octet in octets)


def parse_timeouts(value: Any) -> dict[str, Any]:
    """Decode the ``delay`` field (LED off / lid open / warning, in seconds)."""
    raw = _as_hex(value)
    values: list[int] = []
    for index in range(0, min(len(raw), 6), 2):
        try:
            values.append(int(raw[index : index + 2], 16))
        except ValueError:
            values.append(0)
    while len(values) < len(TIMEOUT_FIELDS):
        values.append(0)
    return {
        "raw": raw,
        **{name: values[index] for index, name in enumerate(TIMEOUT_FIELDS)},
    }


def update_timeouts_hex(value: Any, updates: dict[str, int]) -> str:
    """Return a new ``delay`` hex string with selected timeouts changed."""
    timeouts = parse_timeouts(value)
    values = [max(0, min(255, int(timeouts[name]))) for name in TIMEOUT_FIELDS]
    for name, new_value in updates.items():
        if name in TIMEOUT_FIELDS:
            values[TIMEOUT_FIELDS.index(name)] = max(0, min(255, int(new_value)))
    return "".join(f"{value:02x}" for value in values)


def _safe_time(hour: int, minute: int) -> str | None:
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return time(hour=hour, minute=minute).strftime("%H:%M")
    return None


def parse_custom(value: Any) -> dict[str, Any]:
    """Decode the ``custom`` blob (appointments and unknown trailing bytes)."""
    raw = _as_hex(value)
    octets: list[int | None] = []
    for index in range(0, len(raw), 2):
        chunk = raw[index : index + 2]
        try:
            octets.append(int(chunk, 16))
        except ValueError:
            octets.append(None)

    appointments: dict[str, Any] = {}
    for name, offset in CUSTOM_APPOINTMENTS:
        high = octets[offset] if offset < len(octets) else None
        low = octets[offset + 1] if offset + 1 < len(octets) else None
        if high is None or low is None:
            appointments[name] = None
        elif name in ("unknown_10_11", "unknown_12_13", "unknown_14_15"):
            appointments[name] = f"{high:02x}{low:02x}"
        else:
            appointments[name] = _safe_time(high, low)

    return {"raw": raw, "octets": octets, **appointments}


def parse_stage(value: Any) -> dict[str, Any]:
    """Decode the 10-character ``stage`` blob."""
    raw = _as_hex(value)
    if len(raw) != 10:
        return {
            "raw": raw,
            "state": None,
            "name": "Idle" if raw in ("", "null") else "Unknown stage",
            "description": "",
            "rice_id": None,
            "taste": None,
            "taste_phase": None,
        }

    state = _hex_int(raw[0:2], 0) or 0
    rice_id = _hex_int(raw[2:6], 0) or 0
    taste = _hex_int(raw[6:8], 0) or 0
    stage = COOKING_STAGES.get(state, {"name": "Unknown stage", "description": ""})
    return {
        "raw": raw,
        "state": state,
        "name": stage["name"],
        "description": stage["description"],
        "rice_id": rice_id,
        "taste": taste,
        "taste_phase": min(2, taste // 33),
    }


def parse_temperature(value: Any) -> dict[str, Any]:
    """Decode ``temp`` which is reused for several purposes by the firmware."""
    raw = _as_hex(value)
    result: dict[str, Any] = {"raw": raw, "temperature": None, "start_time": None}

    if len(raw) == 2 and raw.isdigit():
        result["temperature"] = int(raw)
    elif len(raw) >= 8:
        start = _safe_time(
            _hex_int(raw[-4:-2], 255) or 255,
            _hex_int(raw[-2:], 255) or 255,
        )
        result["start_time"] = start
        if len(raw) >= 4:
            result["temperature"] = _hex_int(raw[0:2])
    return result


def parse_version(value: Any) -> dict[str, Any]:
    raw = _as_hex(value)
    hardware = _hex_int(raw[0:4]) if len(raw) >= 4 else None
    firmware = _hex_int(raw[4:8]) if len(raw) >= 8 else None
    return {
        "raw": raw,
        "hardware_version": hardware,
        "firmware_version": firmware,
        "hardware_label": f"{hardware:04x}" if hardware is not None else None,
        "firmware_label": f"{firmware:04x}" if firmware is not None else None,
    }


def _unpack_timer(value: Any) -> dict[str, Any]:
    """Decode the 8-byte ``[seconds][unix timestamp]`` blobs used by cd1."""
    raw = _as_hex(value)
    result: dict[str, Any] = {
        "raw": raw,
        "seconds": None,
        "timestamp": None,
        "datetime": None,
    }
    if len(raw) < 16:
        return result
    first = _hex_int(raw[:8])
    timestamp = _hex_int(raw[8:16])
    result["seconds"] = first
    result["timestamp"] = timestamp
    if timestamp is not None:
        try:
            result["datetime"] = datetime.fromtimestamp(timestamp).isoformat()
        except (ValueError, OSError):
            pass
    return result


def parse_cd1_status(values: list[Any]) -> CookerStatus:
    """Parse the 24-value payload used by ``chunmi.cooker.normalcd1``.

    This firmware uses integer status codes and appends a live Unix timestamp
    to several fields.  Most bytes are still undocumented, so every value is
    kept verbatim as ``raw_00`` .. ``raw_23`` for app-assisted mapping.
    """
    raw: dict[str, Any] = {
        f"raw_{index:02d}": value for index, value in enumerate(values)
    }

    status_code = _int(values[0]) if values else None
    status_name = CD1_STATUS_NAMES.get(status_code, "Unknown")

    code_hex = _as_hex(values[1]) if len(values) > 1 else ""
    cook_mode_code = _hex_int(code_hex[:2]) if code_hex else None
    cook_mode_name = CD1_COOK_MODES.get(cook_mode_code, "Unknown")

    timer = _unpack_timer(values[4] if len(values) > 4 else None)
    reservation = _unpack_timer(values[5] if len(values) > 5 else None)

    start_ts = _int(values[17]) if len(values) > 17 else None
    end_ts = _int(values[19]) if len(values) > 19 else None

    # Meanings confirmed by driving the cooker from Mi Home while watching
    # `get_prop ["all"]` diffs (2026-11-20).
    profile_id = _as_hex(values[1]) if len(values) > 1 else None
    stage_code = _int(values[2]) if len(values) > 2 else None
    cook_minutes = _int(values[3]) if len(values) > 3 else None
    start_flag = _int(values[7]) if len(values) > 7 else None
    heartbeat = _int(values[9]) if len(values) > 9 else None
    run_marker = _int(values[18]) if len(values) > 18 else None

    def _when(timestamp: int | None) -> str | None:
        if timestamp is None:
            return None
        try:
            return datetime.fromtimestamp(timestamp).isoformat()
        except (ValueError, OSError):
            return None

    parsed: dict[str, Any] = {
        "protocol": "miot-cd1",
        "status_code": status_code,
        "status_name": status_name,
        "mode": str(status_code) if status_code is not None else None,
        "mode_name": status_name,
        "cooking": status_code == 2,
        "cook_mode_code": cook_mode_code,
        "cook_mode_name": cook_mode_name,
        "timer_seconds": timer["seconds"],
        "timer_set_at": timer["datetime"],
        "reservation_seconds": reservation["seconds"],
        "reservation_set_at": reservation["datetime"],
        "device_clock": timer["datetime"],
        "last_cook_start": _when(start_ts),
        "last_cook_end": _when(end_ts),
        "profile_id": profile_id,
        "stage_code": stage_code,
        "cook_minutes": cook_minutes,
        "start_flag": start_flag,
        "heartbeat": heartbeat,
        "run_marker": run_marker,
        **raw,
    }
    return CookerStatus(raw=raw, values=list(values), parsed=parsed)


def parse_status(values: list[Any]) -> CookerStatus:
    """Build a tolerant snapshot from the raw ``get_prop ["all"]`` list."""
    if len(values) >= 24:
        return parse_cd1_status(values)
    raw: dict[str, Any] = {}
    for index, field_name in enumerate(STATUS_FIELDS):
        raw[field_name] = values[index] if index < len(values) else None
    for index in range(len(STATUS_FIELDS), len(values)):
        raw[f"raw_{index}"] = values[index]

    func = _as_hex(raw.get("func"))
    stage = parse_stage(raw.get("stage"))
    temp = parse_temperature(raw.get("temp"))
    settings = parse_settings(raw.get("setting"))
    timeouts = parse_timeouts(raw.get("delay"))
    custom = parse_custom(raw.get("custom"))
    version = parse_version(raw.get("version"))
    menu = _hex_int(raw.get("menu"))
    delayed = _int(raw.get("t_precook"))

    parsed: dict[str, Any] = {
        "mode": func,
        "mode_name": MODE_NAMES.get(func.lower(), func or "Unknown"),
        "cooking": func.lower()
        in {"running", "precook", "cooking", "start", "startp", "resume", "resumep"},
        "menu": menu,
        "menu_raw": _as_hex(raw.get("menu")),
        "stage_raw": stage["raw"],
        "stage_state": stage["state"],
        "stage_name": stage["name"],
        "stage_description": stage["description"],
        "rice_id": stage["rice_id"],
        "taste": stage["taste"],
        "taste_phase": stage["taste_phase"],
        "temperature": temp["temperature"],
        "temp_raw": temp["raw"],
        "start_time": temp["start_time"],
        "remaining": _int(raw.get("t_func")),
        "cooking_delayed": delayed if delayed is not None and delayed >= 0 else None,
        "duration": _int(raw.get("t_cook")),
        "settings_raw": settings["raw"],
        "timeouts_raw": timeouts["raw"],
        "custom_raw": custom["raw"],
        "version_raw": version["raw"],
        "hardware_version": version["hardware_version"],
        "firmware_version": version["firmware_version"],
        "hardware_label": version["hardware_label"],
        "firmware_label": version["firmware_label"],
        "favorite": _hex_int(raw.get("favorite")),
        "favorite_raw": _as_hex(raw.get("favorite")),
        "settings": settings,
        "timeouts": timeouts,
        "custom": custom,
        "appointments": {
            name: custom[name]
            for name, _ in CUSTOM_APPOINTMENTS
            if name not in {"unknown_10_11", "unknown_12_13", "unknown_14_15"}
        },
        **{
            name: custom[name]
            for name, _ in CUSTOM_APPOINTMENTS
            if name not in {"unknown_10_11", "unknown_12_13", "unknown_14_15"}
        },
        **{f"flag_{name}": flags for name, flags in settings["flags"].items()},
    }
    return CookerStatus(raw=raw, values=list(values), parsed=parsed)


def parse_temperature_history(value: Any) -> list[int]:
    """Decode ``get_temp_history`` hex string into temperatures."""
    raw = _as_hex(value)
    if len(raw) % 2:
        return []
    result: list[int] = []
    for index in range(0, len(raw), 2):
        parsed = _hex_int(raw[index : index + 2])
        if parsed is not None:
            result.append(parsed)
    return result
