"""Voluptuous schemas for xiaomi_cooker_local services."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_DEVICE_ID,
    ATTR_FAVORITES_ONLY,
    ATTR_LANGUAGE,
    ATTR_LIMIT,
    ATTR_METHOD,
    ATTR_PARAMETERS,
    ATTR_PROFILE,
    ATTR_QUERY,
    ATTR_RECIPE,
    SERVICE_ADD_FAVORITE,
    SERVICE_DUMP,
    SERVICE_GET_RECIPE,
    SERVICE_GET_TEMPERATURE_HISTORY,
    SERVICE_LIST_FAVORITES,
    SERVICE_RAW_COMMAND,
    SERVICE_REFRESH_RECIPES,
    SERVICE_REMOVE_FAVORITE,
    SERVICE_SEARCH_RECIPES,
    SERVICE_SET_MENU,
    SERVICE_SET_RECIPE_LANGUAGE,
    SERVICE_SET_SETTINGS,
    SERVICE_SET_TIMEOUTS,
    SERVICE_START,
    SERVICE_START_RECIPE,
    SERVICE_STOP,
    SERVICE_TRANSLATE_RECIPE,
)
from .parsing import TIMEOUT_FIELDS, WRITABLE_SETTINGS

_TARGET_SCHEMA = {
    # HA may pass a single device ID or a list when a target selector is used.
    vol.Optional(ATTR_DEVICE_ID): vol.Any(cv.string, [cv.string]),
    vol.Optional(ATTR_ENTITY_ID): cv.entity_ids,
}

SERVICE_SCHEMAS = {
    SERVICE_START: vol.Schema(
        {
            **_TARGET_SCHEMA,
            vol.Optional(ATTR_PROFILE): cv.string,
        }
    ),
    SERVICE_STOP: vol.Schema(_TARGET_SCHEMA),
    SERVICE_RAW_COMMAND: vol.Schema(
        {
            **_TARGET_SCHEMA,
            vol.Required(ATTR_METHOD): cv.string,
            vol.Optional(ATTR_PARAMETERS, default=[]): vol.Any(list, dict, str, int),
        }
    ),
    SERVICE_DUMP: vol.Schema(_TARGET_SCHEMA),
    SERVICE_SET_MENU: vol.Schema(
        {
            **_TARGET_SCHEMA,
            vol.Required(ATTR_PROFILE): cv.string,
        }
    ),
    SERVICE_SET_SETTINGS: vol.Schema(
        {
            **_TARGET_SCHEMA,
            **{vol.Optional(name): cv.boolean for name in WRITABLE_SETTINGS},
        }
    ),
    SERVICE_SET_TIMEOUTS: vol.Schema(
        {
            **_TARGET_SCHEMA,
            **{
                vol.Optional(name): vol.All(vol.Coerce(int), vol.Range(min=0, max=255))
                for name in TIMEOUT_FIELDS
            },
        }
    ),
    SERVICE_GET_TEMPERATURE_HISTORY: vol.Schema(_TARGET_SCHEMA),
    SERVICE_SEARCH_RECIPES: vol.Schema(
        {
            **_TARGET_SCHEMA,
            vol.Required(ATTR_QUERY, default=""): cv.string,
            vol.Optional(ATTR_LIMIT, default=20): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=100)
            ),
            vol.Optional(ATTR_FAVORITES_ONLY, default=False): cv.boolean,
        }
    ),
    SERVICE_GET_RECIPE: vol.Schema(
        {
            **_TARGET_SCHEMA,
            vol.Optional(ATTR_RECIPE): vol.Any(cv.string, vol.Coerce(int)),
            vol.Optional(ATTR_LANGUAGE): vol.In(["ha", "original"]),
        }
    ),
    SERVICE_START_RECIPE: vol.Schema(
        {
            **_TARGET_SCHEMA,
            vol.Optional(ATTR_RECIPE): vol.Any(cv.string, vol.Coerce(int)),
        }
    ),
    SERVICE_TRANSLATE_RECIPE: vol.Schema(
        {
            **_TARGET_SCHEMA,
            vol.Optional(ATTR_RECIPE): vol.Any(cv.string, vol.Coerce(int)),
        }
    ),
    SERVICE_ADD_FAVORITE: vol.Schema(
        {
            **_TARGET_SCHEMA,
            vol.Optional(ATTR_RECIPE): vol.Any(cv.string, vol.Coerce(int)),
        }
    ),
    SERVICE_REMOVE_FAVORITE: vol.Schema(
        {
            **_TARGET_SCHEMA,
            vol.Optional(ATTR_RECIPE): vol.Any(cv.string, vol.Coerce(int)),
        }
    ),
    SERVICE_LIST_FAVORITES: vol.Schema(_TARGET_SCHEMA),
    SERVICE_REFRESH_RECIPES: vol.Schema(_TARGET_SCHEMA),
    SERVICE_SET_RECIPE_LANGUAGE: vol.Schema(
        {
            **_TARGET_SCHEMA,
            vol.Required(ATTR_LANGUAGE): vol.In(["ha", "original"]),
        }
    ),
}
