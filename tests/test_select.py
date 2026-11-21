"""Regression tests for the cooker select entities."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.xiaomi_cooker_local.const import MODEL_CD1
from custom_components.xiaomi_cooker_local.select import (
    CookerModeSelect,
    CookerProfileSelect,
)


def _entry(model: str = MODEL_CD1):
    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.data = {"model": model, "name": "Rice Cooker"}
    entry.options = {}
    return entry


def test_cook_mode_select_constructs_with_description() -> None:
    coordinator = MagicMock()
    select = CookerModeSelect(coordinator, _entry())

    assert select.entity_description.key == "cook_mode"
    assert select.unique_id == "entry-1_cook_mode"
    assert set(select.options) == {
        "Fine Cook",
        "Quick Cook",
        "Cook Congee",
        "Keep Warm",
    }


def test_profile_select_constructs_with_description() -> None:
    coordinator = MagicMock()
    select = CookerProfileSelect(coordinator, _entry())

    assert select.entity_description.key == "profile"
    assert select.unique_id == "entry-1_profile"
