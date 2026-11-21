"""Constants for the Xiaomi Rice Cooker (local miio) integration."""

from __future__ import annotations

DOMAIN = "xiaomi_cooker_local"
MANUFACTURER = "Xiaomi"
DEFAULT_NAME = "Rice Cooker"

CONF_TOKEN = "token"
CONF_MODEL = "model"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_TIMEOUT = "timeout"
CONF_PROFILES = "profiles"
CONF_RECIPE_SOURCE = "recipe_source"

DEFAULT_SCAN_INTERVAL = 30
DEFAULT_TIMEOUT = 5
MIN_SCAN_INTERVAL = 5
MAX_TIMEOUT = 60

# Field order returned by `get_prop ["all"]` on chunmi.cooker.* devices.
# Some firmwares return more values; extras are kept as raw_N by the parser.
STATUS_FIELDS: tuple[str, ...] = (
    "func",
    "menu",
    "stage",
    "temp",
    "t_func",
    "t_precook",
    "t_cook",
    "setting",
    "delay",
    "version",
    "favorite",
    "custom",
)

KNOWN_MODELS: tuple[str, ...] = (
    "chunmi.cooker.normal1",
    "chunmi.cooker.normal2",
    "chunmi.cooker.normal3",
    "chunmi.cooker.normal4",
    "chunmi.cooker.normal5",
    "chunmi.cooker.press1",
    "chunmi.cooker.press2",
    "chunmi.cooker.eh1",
    "chunmi.pre_cooker.eh1",
    "chunmi.cooker.normalcd1",
)

MODEL_CD1 = "chunmi.cooker.normalcd1"

PLATFORMS: list[str] = [
    "binary_sensor",
    "button",
    "number",
    "select",
    "sensor",
    "switch",
    "text",
]

# Recipe library
RECIPE_SOURCE_CACHE = "cache"
RECIPE_SOURCE_API = "api"
RECIPE_SOURCE_JSON = "json"
RECIPE_LANGUAGE_HA = "ha"
RECIPE_LANGUAGE_ORIGINAL = "original"
DEFAULT_RECIPE_SOURCE = RECIPE_SOURCE_CACHE
DEFAULT_RECIPE_LANGUAGE = RECIPE_LANGUAGE_HA

SERVICE_START = "start"
SERVICE_STOP = "stop"
SERVICE_RAW_COMMAND = "raw_command"
SERVICE_DUMP = "dump"
SERVICE_SET_SETTINGS = "set_settings"
SERVICE_SET_TIMEOUTS = "set_timeouts"
SERVICE_SET_MENU = "set_menu"
SERVICE_GET_TEMPERATURE_HISTORY = "get_temperature_history"
SERVICE_SEARCH_RECIPES = "search_recipes"
SERVICE_GET_RECIPE = "get_recipe"
SERVICE_START_RECIPE = "start_recipe"
SERVICE_ADD_FAVORITE = "add_favorite"
SERVICE_REMOVE_FAVORITE = "remove_favorite"
SERVICE_LIST_FAVORITES = "list_favorites"
SERVICE_REFRESH_RECIPES = "refresh_recipes"
SERVICE_SET_RECIPE_LANGUAGE = "set_recipe_language"
SERVICE_TRANSLATE_RECIPE = "translate_recipe"
ATTR_PROFILE = "profile"
ATTR_METHOD = "method"
ATTR_PARAMETERS = "parameters"
ATTR_DEVICE_ID = "device_id"
ATTR_DURATION = "duration"
ATTR_QUERY = "query"
ATTR_RECIPE = "recipe"
ATTR_LIMIT = "limit"
ATTR_FAVORITES_ONLY = "favorites_only"
ATTR_LANGUAGE = "language"

DATA_CLIENT = "client"
DATA_COORDINATOR = "coordinator"
DATA_SELECTED_PROFILE = "selected_profile"
DATA_LAST_DUMP = "last_dump"
DATA_RECIPES = "recipes"
DATA_RECIPE_QUERY = "recipe_query"
DATA_ACTIVE_RECIPE_ID = "active_recipe_id"
