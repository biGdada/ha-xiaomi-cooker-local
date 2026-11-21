"""Tests for the cooking profile helpers."""

from __future__ import annotations

import pytest

from custom_components.xiaomi_cooker_local.profiles import (
    custom_profiles,
    is_valid_profile,
    profile_titles,
    profiles_for_model,
    resolve_profile,
)


def test_profile_groups() -> None:
    assert profiles_for_model("chunmi.cooker.press1")[0]["group"] == "MODEL_PRESSURE"
    assert (
        profiles_for_model("chunmi.cooker.normal2")[0]["group"]
        == "MODEL_NORMAL_GROUP1"
    )
    assert (
        profiles_for_model("chunmi.cooker.normal3")[0]["group"]
        == "MODEL_NORMAL_GROUP2"
    )


def test_resolve_by_title() -> None:
    model = "chunmi.cooker.normal2"
    resolved = resolve_profile(model, "Jingzhu")
    assert is_valid_profile(resolved)
    assert resolved == profiles_for_model(model)[0]["profile"].lower()


def test_resolve_raw_hex() -> None:
    profile = profiles_for_model("chunmi.cooker.normal2")[0]["profile"]
    assert resolve_profile(None, profile) == profile.lower()


def test_custom_profiles_from_json() -> None:
    profile = profiles_for_model("chunmi.cooker.normal2")[0]["profile"]
    raw = [{"title": "My rice", "profile": profile, "description": "test"}]
    assert custom_profiles(raw)[0]["title"] == "My rice"
    assert "My rice" in profile_titles("chunmi.cooker.normal2", raw)


def test_invalid_profile_raises() -> None:
    with pytest.raises(ValueError):
        resolve_profile(None, "abcd")
