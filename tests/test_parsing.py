"""Tests for the tolerant raw payload parser."""

from __future__ import annotations

from custom_components.xiaomi_cooker_local.parsing import (
    parse_custom,
    parse_settings,
    parse_stage,
    parse_status,
    parse_temperature_history,
    parse_timeouts,
    update_settings_hex,
    update_timeouts_hex,
)

IDLE = [
    "waiting",
    "0001",
    "null",
    "29",
    "60",
    "-1",
    "60",
    "0607",
    "05040f",
    "00030017",
    "0100",
    "ffffffffffff011effff010000001d1f",
]

COOKING = [
    "running",
    "0001",
    "02000000ff",
    "031e0b23",
    "54",
    "-1",
    "60",
    "0607",
    "05040f",
    "00030017",
    "0100",
    "ffffffffffff011effff010002013e23",
    "extra-value",
]


def test_idle_snapshot() -> None:
    status = parse_status(IDLE)
    assert status.parsed["mode"] == "waiting"
    assert status.parsed["mode_name"] == "Idle"
    assert status.parsed["cooking"] is False
    assert status.parsed["temperature"] == 29
    assert status.parsed["menu"] == 1
    assert status.parsed["stage_name"] == "Idle"
    assert status.parsed["remaining"] == 60
    assert status.parsed["cooking_delayed"] is None
    assert status.parsed["firmware_label"] == "0017"
    assert status.parsed["hardware_label"] == "0003"


def test_cooking_snapshot_with_extra_field() -> None:
    status = parse_status(COOKING)
    assert status.parsed["mode_name"] == "Cooking"
    assert status.parsed["cooking"] is True
    assert status.parsed["stage_name"] == "Boiling"
    assert status.parsed["rice_id"] == 0
    assert status.parsed["start_time"] == "11:35"
    assert status.raw["raw_12"] == "extra-value"


def test_unknown_mode_does_not_raise() -> None:
    values = list(IDLE)
    values[0] = "brandnewmode"
    status = parse_status(values)
    assert status.parsed["mode"] == "brandnewmode"
    assert status.parsed["mode_name"] == "brandnewmode"


def test_settings_flags_and_updates() -> None:
    settings = parse_settings("1407")
    assert settings["led_on"] is False
    assert settings["auto_keep_warm"] is True
    assert settings["pressure_supported"] is False
    assert settings["lid_open_warning"] is False
    assert settings["lid_open_warning_delayed"] is True

    updated = update_settings_hex("0607", {"led_on": True, "auto_keep_warm": False})
    assert updated == "0207"
    assert parse_settings(updated)["led_on"] is True
    assert parse_settings(updated)["auto_keep_warm"] is False


def test_timeouts() -> None:
    timeouts = parse_timeouts("05040f")
    assert timeouts["led_off"] == 5
    assert timeouts["lid_open"] == 4
    assert timeouts["lid_open_warning"] == 15
    assert update_timeouts_hex("05040f", {"lid_open": 9}) == "05090f"


def test_custom_appointments_are_safe() -> None:
    custom = parse_custom("ffffffffffff011effff010000001d1f")
    assert custom["jingzhu_appointment"] is None
    assert custom["favorite_appointment"] == "01:30"
    status = parse_status(IDLE)
    assert status.parsed["favorite_appointment"] == "01:30"
    assert status.parsed["jingzhu_appointment"] is None


def test_stage_unknown() -> None:
    stage = parse_stage("ff000000ff")
    assert stage["name"] == "Unknown stage"
    assert stage["state"] == 255


def test_cd1_payload_is_not_parsed_as_classic() -> None:
    values = [
        1,
        "0100000002",
        11,
        40,
        "0000095c6b001217",
        "000000006b001217",
        "1100",
        0,
        0,
        25,
        1,
        2,
        2,
        0,
        0,
        1,
        3,
        1794849417,
        1,
        1794851615,
        0,
        "000a570a",
        "00000bc3",
        2,
    ]
    status = parse_status(values)
    assert status.parsed["protocol"] == "miot-cd1"
    assert status.parsed["status_name"] == "Idle"
    assert status.parsed["cooking"] is False
    assert status.parsed["timer_seconds"] == 2396
    assert status.parsed["timer_set_at"] == "2026-11-20T11:25:43"
    assert status.parsed["device_clock"] == "2026-11-20T11:25:43"
    assert status.parsed["last_cook_start"] == "2026-11-16T19:16:57"
    assert status.parsed["last_cook_end"] == "2026-11-16T19:53:35"
    assert status.parsed["raw_00"] == 1
    assert status.parsed["raw_23"] == 2
    assert status.parsed.get("temperature") is None


def test_temperature_history() -> None:
    assert parse_temperature_history("161515") == [22, 21, 21]
    assert parse_temperature_history("161") == []
