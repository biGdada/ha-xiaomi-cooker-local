"""Helpers for importing an existing miIO token from Home Assistant.

The cooker cannot return its token over local discovery: the token is the
encryption key for the miIO protocol. If another Xiaomi integration already
stored it for the same IP, we can reuse it without cloud credentials.

Two sources are checked:

1. Config entry data/options (Xiaomi MiIO host/token entries, Xiaomi Miot Auto
   host/token entries).
2. Runtime data in ``hass.data`` (Xiaomi Miot Auto entries added via a Mi
   Account keep per-device host/token pairs there, not in entry data).
"""

from __future__ import annotations

from typing import Any

TOKEN_IMPORT_DOMAINS: tuple[str, ...] = (
    "xiaomi_miio",
    "xiaomi_miot",
    "xiaomi_miot_auto",
)

TOKEN_KEYS: tuple[str, ...] = ("token", "miio_token", "miioToken", "device_token")
HOST_KEYS: tuple[str, ...] = (
    "host",
    "ip",
    "address",
    "device_host",
    "localip",
    "host_ip",
)

_MAX_RUNTIME_DEPTH = 8


def _norm_host(value: Any) -> str:
    return str(value or "").strip().lower()


def _entry_data(entry: Any) -> dict[str, Any]:
    return {
        **(getattr(entry, "data", None) or {}),
        **(getattr(entry, "options", None) or {}),
    }


def _token_from_mapping(data: dict[str, Any], target: str) -> str | None:
    hosts = {_norm_host(data.get(key)) for key in HOST_KEYS}
    if target not in hosts:
        return None
    for key in TOKEN_KEYS:
        token = str(data.get(key) or "").strip()
        if token:
            return token
    return None


def _iter_dicts(value: Any, depth: int = 0) -> Any:
    """Yield dictionaries nested in runtime data, with a depth guard."""
    if depth > _MAX_RUNTIME_DEPTH:
        return
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_dicts(child, depth + 1)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _iter_dicts(child, depth + 1)


def find_saved_token(
    entries_by_domain: dict[str, list[Any]],
    host: str,
    runtime_by_domain: dict[str, Any] | None = None,
) -> tuple[str | None, str | None]:
    """Return ``(token, domain)`` for a saved entry matching ``host``."""
    target = _norm_host(host)
    if not target:
        return None, None

    for domain in TOKEN_IMPORT_DOMAINS:
        for entry in entries_by_domain.get(domain) or []:
            token = _token_from_mapping(_entry_data(entry), target)
            if token:
                return token, domain

    for domain in TOKEN_IMPORT_DOMAINS:
        runtime = (runtime_by_domain or {}).get(domain)
        if not runtime:
            continue
        for data in _iter_dicts(runtime):
            token = _token_from_mapping(data, target)
            if token:
                return token, domain

    return None, None
