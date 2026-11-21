"""Service target fields accept HA's scalar and list forms."""

from __future__ import annotations

from homeassistant.const import ATTR_ENTITY_ID

from custom_components.xiaomi_cooker_local.const import (
    ATTR_DEVICE_ID,
    SERVICE_SEARCH_RECIPES,
)
from custom_components.xiaomi_cooker_local.service_schema import SERVICE_SCHEMAS


def test_device_id_accepts_string_and_list() -> None:
    schema = SERVICE_SCHEMAS[SERVICE_SEARCH_RECIPES]

    assert schema({ATTR_DEVICE_ID: "device-1"})[ATTR_DEVICE_ID] == "device-1"
    assert schema({ATTR_DEVICE_ID: ["device-1"]})[ATTR_DEVICE_ID] == ["device-1"]


def test_entity_id_accepts_string_and_list() -> None:
    schema = SERVICE_SCHEMAS[SERVICE_SEARCH_RECIPES]

    assert schema({ATTR_ENTITY_ID: "sensor.cooker_status"})[ATTR_ENTITY_ID] == [
        "sensor.cooker_status"
    ]
    assert schema({ATTR_ENTITY_ID: ["sensor.cooker_status"]})[ATTR_ENTITY_ID] == [
        "sensor.cooker_status"
    ]
