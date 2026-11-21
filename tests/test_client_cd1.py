"""Tests for the confirmed cd1 legacy command path."""

from __future__ import annotations

from unittest.mock import Mock

from custom_components.xiaomi_cooker_local.client import CookerClient

CD1 = "chunmi.cooker.normalcd1"


def test_cd1_mode_translation() -> None:
    assert CookerClient.cd1_mode(None) == 2
    assert CookerClient.cd1_mode(3) == 3
    assert CookerClient.cd1_mode("1") == 1
    assert CookerClient.cd1_mode("Cook Congee") == 3
    assert CookerClient.cd1_mode("nonsense") == 2


def test_cd1_start_and_stop_use_legacy_methods() -> None:
    client = CookerClient("host", "token", model=CD1)
    client.raw_command = Mock(return_value=[1])

    assert client.start("Fine Cook") == [1]
    client.raw_command.assert_called_with("start_cook", [1])

    assert client.stop() == [1]
    client.raw_command.assert_called_with("cancel_cooking", [])


def test_start_cookcode_uses_local_set_start() -> None:
    client = CookerClient("host", "token", model=CD1)
    client.raw_command = Mock(return_value=[1])
    code = "ab" * 133

    assert client.start_cookcode(code) == [1]
    client.raw_command.assert_called_with("set_start", [code])

    try:
        client.start_cookcode("aa")
    except ValueError:
        pass
    else:
        raise AssertionError("short cookcode should be rejected")


def test_classic_commands_are_unchanged() -> None:
    client = CookerClient("host", "token", model="chunmi.cooker.normal2")
    client.raw_command = Mock(return_value=[1])

    client.start("0001E1010000")
    client.raw_command.assert_called_with("set_start", ["0001E1010000"])

    client.stop()
    client.raw_command.assert_called_with("set_func", ["end02"])
