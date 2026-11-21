"""Tests for importing an existing miIO token from HA config entries."""

from __future__ import annotations

from types import SimpleNamespace

from custom_components.xiaomi_cooker_local.token_import import find_saved_token


def test_find_saved_token_by_host_and_key_variants() -> None:
    entries = {
        "xiaomi_miio": [
            SimpleNamespace(
                data={"host": "192.168.1.10", "token": "a" * 32}, options={}
            )
        ],
        "xiaomi_miot": [
            SimpleNamespace(
                data={"ip": "192.168.1.20", "miio_token": "b" * 32}, options={}
            )
        ],
    }

    assert find_saved_token(entries, "192.168.1.10") == ("a" * 32, "xiaomi_miio")
    assert find_saved_token(entries, "192.168.1.20") == ("b" * 32, "xiaomi_miot")
    assert find_saved_token(entries, "192.168.1.99") == (None, None)
    assert find_saved_token(entries, "") == (None, None)


def test_options_override_and_missing_entries() -> None:
    entries = {
        "xiaomi_miio": [
            SimpleNamespace(
                data={"host": "192.168.1.30", "token": "old"},
                options={"token": "new-token"},
            )
        ]
    }

    assert find_saved_token(entries, "192.168.1.30") == ("new-token", "xiaomi_miio")
    assert find_saved_token({}, "192.168.1.30") == (None, None)


def test_find_saved_token_in_miot_account_runtime_data() -> None:
    """Miot account entries keep per-device tokens in hass.data, not entry data."""
    runtime = {
        "xiaomi_miot": {
            "abc123": {
                "configs": [
                    {"host": "192.168.1.40", "token": "c" * 32, "model": "x.y.z"},
                    {"host": "192.168.1.41", "token": "d" * 32},
                ]
            }
        }
    }

    assert find_saved_token({}, "192.168.1.40", runtime) == ("c" * 32, "xiaomi_miot")
    assert find_saved_token({}, "192.168.1.41", runtime) == ("d" * 32, "xiaomi_miot")
    assert find_saved_token({}, "192.168.1.99", runtime) == (None, None)
