"""Config and options flows for the local Xiaomi cooker integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .client import CookerClient
from .const import (
    CONF_MODEL,
    CONF_PROFILES,
    CONF_RECIPE_SOURCE,
    CONF_SCAN_INTERVAL,
    CONF_TIMEOUT,
    CONF_TOKEN,
    DEFAULT_NAME,
    DEFAULT_RECIPE_SOURCE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
    KNOWN_MODELS,
    MAX_TIMEOUT,
    MIN_SCAN_INTERVAL,
    RECIPE_SOURCE_API,
    RECIPE_SOURCE_CACHE,
    RECIPE_SOURCE_JSON,
)
from .profiles import custom_profiles
from .token_import import TOKEN_IMPORT_DOMAINS, find_saved_token

_LOGGER = logging.getLogger(__name__)


async def _validate_input(hass, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the connection and return device info."""
    client = CookerClient(
        host=data["host"],
        token=data["token"],
        model=data.get(CONF_MODEL) or None,
        timeout=data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
    )
    try:
        info = await hass.async_add_executor_job(client.probe)
    except Exception as probe_err:
        _LOGGER.debug("Probe failed, trying status-only validation", exc_info=True)
        if not data.get(CONF_MODEL):
            raise CannotConnect from probe_err
        try:
            await hass.async_add_executor_job(client.status)
        except Exception as status_err:
            raise CannotConnect from status_err
        info = {"model": data[CONF_MODEL]}

    try:
        await hass.async_add_executor_job(client.close)
    except Exception:  # pragma: no cover
        pass

    if not info.get("model") and data.get(CONF_MODEL):
        info["model"] = data[CONF_MODEL]
    info["model"] = info.get("model") or "unknown"
    return info


class CannotConnect(Exception):
    """Unable to reach the cooker with the supplied settings."""


class TokenNotFound(Exception):
    """No saved miIO token was found for this host."""


def _saved_token_for_host(hass, host: str) -> str | None:
    """Find a miIO token already stored in HA for the same IP address."""
    entries_by_domain = {
        domain: list(hass.config_entries.async_entries(domain))
        for domain in TOKEN_IMPORT_DOMAINS
    }
    runtime_by_domain = {
        domain: hass.data.get(domain) for domain in TOKEN_IMPORT_DOMAINS
    }
    token, domain = find_saved_token(entries_by_domain, host, runtime_by_domain)
    if token and domain:
        _LOGGER.info("Imported miIO token from %s config entry", domain)
    return token


class XiaomiCookerLocalConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for a Xiaomi cooker."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            submitted = dict(user_input)
            token = str(submitted.get(CONF_TOKEN) or "").strip()
            if not token:
                token = _saved_token_for_host(
                    self.hass, str(submitted.get(CONF_HOST) or "")
                )
                if token:
                    submitted[CONF_TOKEN] = token
                else:
                    errors["base"] = "token_not_found"
            if not errors:
                try:
                    info = await _validate_input(self.hass, submitted)
                except CannotConnect:
                    errors["base"] = "cannot_connect"
            if not errors:
                identifier = (
                    info.get("device_id")
                    or info.get("mac_address")
                    or submitted[CONF_HOST]
                )
                await self.async_set_unique_id(str(identifier).lower())
                self._abort_if_unique_id_configured()

                model = info.get("model") or submitted.get(CONF_MODEL)
                data = {
                    **submitted,
                    CONF_MODEL: model,
                }
                return self.async_create_entry(
                    title=submitted.get("name") or DEFAULT_NAME,
                    data=data,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): selector.TextSelector(),
                    vol.Optional(CONF_TOKEN, default=""): selector.TextSelector(),
                    vol.Optional("name", default=DEFAULT_NAME): selector.TextSelector(),
                    vol.Optional(CONF_MODEL, default=""): selector.TextSelector(),
                    vol.Optional(
                        CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                    ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)),
                    vol.Optional(
                        CONF_TIMEOUT, default=DEFAULT_TIMEOUT
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_TIMEOUT)),
                }
            ),
            errors=errors,
            description_placeholders={
                "known_models": ", ".join(KNOWN_MODELS),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return XiaomiCookerLocalOptionsFlow(config_entry)


class XiaomiCookerLocalOptionsFlow(OptionsFlow):
    """Options for polling and user supplied profiles."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            raw_profiles = user_input.get(CONF_PROFILES, "")
            if raw_profiles:
                import json

                try:
                    parsed = json.loads(raw_profiles)
                except json.JSONDecodeError:
                    errors[CONF_PROFILES] = "invalid_profiles"
                else:
                    if not custom_profiles(parsed):
                        errors[CONF_PROFILES] = "invalid_profiles"
            if not errors:
                return self.async_create_entry(title="", data=user_input)

        current = {**self._config_entry.data, **self._config_entry.options}
        raw_current = current.get(CONF_PROFILES, "")
        if isinstance(raw_current, (list, dict)):
            import json

            raw_current = json.dumps(raw_current, indent=2)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=current.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)),
                    vol.Optional(
                        CONF_TIMEOUT,
                        default=current.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_TIMEOUT)),
                    vol.Optional(
                        CONF_PROFILES, default=raw_current
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(multiline=True)
                    ),
                    vol.Optional(
                        CONF_RECIPE_SOURCE,
                        default=current.get(
                            CONF_RECIPE_SOURCE, DEFAULT_RECIPE_SOURCE
                        ),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(
                                    value=RECIPE_SOURCE_CACHE,
                                    label="Cache (first run and after updates)",
                                ),
                                selector.SelectOptionDict(
                                    value=RECIPE_SOURCE_API,
                                    label="Every Home Assistant start",
                                ),
                                selector.SelectOptionDict(
                                    value=RECIPE_SOURCE_JSON,
                                    label="Bundled JSON only",
                                ),
                            ]
                        )
                    ),
                }
            ),
            errors=errors,
        )
