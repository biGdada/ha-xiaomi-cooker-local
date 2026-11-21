#!/usr/bin/env python3
"""Standalone miIO cooker probe — use this to map features with the Mi Home app.

Requires only python-miio (no Home Assistant):

    pip install python-miio==0.5.12

Examples:

    python tools/cooker_probe.py --host 192.168.1.50 --token TOKEN info
    python tools/cooker_probe.py --host ... --token ... status
    python tools/cooker_probe.py --host ... --token ... watch --interval 1
    python tools/cooker_probe.py --host ... --token ... watch --log-file map.jsonl
    python tools/cooker_probe.py --host ... --token ... raw get_prop '["all"]'
    python tools/cooker_probe.py --host ... --token ... methods
    python tools/cooker_probe.py --host ... --token ... start --mode 2
    python tools/cooker_probe.py --host ... --token ... stop
    python tools/cooker_probe.py --host ... --token ... dump --output dump.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from miio import Device
    from miio.exceptions import DeviceException
except ImportError:
    sys.exit("Install python-miio first: pip install python-miio==0.5.12")


FIELDS = (
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

PROBE_METHODS: tuple[tuple[str, Any], ...] = (
    ("get_prop", ["all"]),
    ("get_temp_history", None),
    ("get_interaction", None),
    ("get_customization", None),
    ("get_menu", None),
    ("get_func", None),
    ("get_device_info", None),
    ("miIO.info", None),
)


def connect(args: argparse.Namespace) -> Device:
    return Device(
        args.host,
        args.token,
        timeout=args.timeout,
        model=args.model or None,
        lazy_discover=True,
    )


def raw_values(device: Device) -> list[Any]:
    response = device.send("get_prop", ["all"])
    if not isinstance(response, (list, tuple)):
        raise DeviceException(f"Unexpected get_prop result: {response!r}")
    return list(response)


def labelled(values: list[Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for index, value in enumerate(values):
        name = FIELDS[index] if index < len(FIELDS) else f"raw_{index}"
        result[f"[{index:02d}] {name}"] = value
    return result


def printable(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def info_command(device: Device, args: argparse.Namespace) -> None:
    info = device.info()
    print("== device info ==")
    for name in (
        "model",
        "device_id",
        "mac_address",
        "hardware_version",
        "firmware_version",
        "local_ip",
    ):
        value = getattr(info, name, None)
        if value is not None:
            print(f"{name:20s}: {value}")
    print(f"{'raw':20s}: {info!r}")


def status_command(device: Device, args: argparse.Namespace) -> None:
    values = raw_values(device)
    print(f"== raw get_prop ['all'] ({len(values)} values) ==")
    for key, value in labelled(values).items():
        print(f"{key:24s}: {printable(value)}")


def watch_command(device: Device, args: argparse.Namespace) -> None:
    log_file = Path(args.log_file) if args.log_file else None
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + args.seconds if args.seconds else None
    previous: list[Any] | None = None
    print(
        f"Watching {args.host} every {args.interval}s. "
        "Now tap buttons in Mi Home and watch the diffs. Ctrl-C to stop."
    )
    try:
        while deadline is None or time.monotonic() < deadline:
            try:
                values = raw_values(device)
            except Exception as err:
                print(f"{timestamp()} ERROR {err}", flush=True)
            else:
                if previous is None or values != previous:
                    now = timestamp()
                    print(f"\n== {now} ==", flush=True)
                    if previous is None:
                        for key, value in labelled(values).items():
                            print(f"  {key:24s}: {printable(value)}")
                    else:
                        for index, value in enumerate(values):
                            old = previous[index] if index < len(previous) else None
                            if old != value:
                                name = (
                                    FIELDS[index]
                                    if index < len(FIELDS)
                                    else f"raw_{index}"
                                )
                                print(
                                    f"  [{index:02d}] {name:16s}: "
                                    f"{printable(old)} -> {printable(value)}"
                                )
                    if log_file:
                        record = {
                            "timestamp": now,
                            "values": values,
                            "labelled": labelled(values),
                        }
                        with log_file.open("a", encoding="utf-8") as file:
                            file.write(json.dumps(record, ensure_ascii=False) + "\n")
                    previous = values
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")


def raw_command(device: Device, args: argparse.Namespace) -> None:
    try:
        parameters = json.loads(args.parameters)
    except json.JSONDecodeError:
        sys.exit("parameters must be valid JSON (e.g. '[\"all\"]')")
    print(f"== {args.method} {parameters!r} ==")
    try:
        result = device.send(args.method, parameters)
    except Exception as err:
        print(f"ERROR: {type(err).__name__}: {err}")
        return
    print(printable(result))


def methods_command(device: Device, args: argparse.Namespace) -> None:
    print("== probing methods ==")
    for method, parameters in PROBE_METHODS:
        try:
            result = device.send(method, parameters)
        except Exception as err:
            print(f"{method:24s}: ERROR {type(err).__name__}: {err}")
        else:
            text = printable(result)
            if len(text) > 160:
                text = text[:160] + "..."
            print(f"{method:24s}: {text}")


def control_command(device: Device, args: argparse.Namespace) -> None:
    """Start/stop using the legacy methods confirmed on cd1 firmware."""
    if args.command == "start":
        method: str = "start_cook"
        parameters: Any = [args.mode]
    else:
        method = "cancel_cooking"
        parameters = []
    print(f"== {method} {parameters!r} ==")
    try:
        result = device.send(method, parameters)
    except Exception as err:
        print(f"ERROR: {type(err).__name__}: {err}")
        return
    print(f"-> {printable(result)}")
    time.sleep(1)  # cd1 publishes the new state a moment after acknowledging
    print("status:", device.send("get_prop", ["status"]))


def dump_command(device: Device, args: argparse.Namespace) -> None:
    info = device.info()
    values = raw_values(device)
    snapshot = {
        "timestamp": datetime.now(UTC).isoformat(),
        "host": args.host,
        "model": args.model or getattr(info, "model", None),
        "info": repr(info),
        "raw_values": values,
        "labelled": labelled(values),
    }
    path = Path(args.output or f"cooker_dump_{int(time.time())}.json")
    path.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Wrote {path}")


def timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="Cooker IP address")
    parser.add_argument("--token", required=True, help="32-character miIO token")
    parser.add_argument("--model", help="Override model (skips auto-detection)")
    parser.add_argument("--timeout", type=int, default=5, help="Socket timeout (s)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("info", help="Show device info and detected model")
    subparsers.add_parser("status", help="Show one raw status snapshot")

    watch = subparsers.add_parser("watch", help="Poll and print state changes")
    watch.add_argument("--interval", type=float, default=1.0, help="Poll interval (s)")
    watch.add_argument(
        "--seconds", type=int, default=0, help="Stop after N seconds (0 = never)"
    )
    watch.add_argument("--log-file", help="Append every changed snapshot as JSONL")

    raw = subparsers.add_parser("raw", help="Send a raw miIO command")
    raw.add_argument("method", help="miIO method name")
    raw.add_argument("parameters", nargs="?", default="[]", help="JSON parameters")

    subparsers.add_parser("methods", help="Probe a list of known cooker methods")
    start = subparsers.add_parser("start", help="Start cooking (cd1 legacy method)")
    start.add_argument(
        "--mode", type=int, default=2, choices=(1, 2, 3, 4),
        help="1=Fine Cook, 2=Quick Cook, 3=Cook Congee, 4=Keep Warm",
    )
    subparsers.add_parser("stop", help="Cancel cooking (cd1 legacy method)")
    dump = subparsers.add_parser("dump", help="Write a JSON snapshot to disk")
    dump.add_argument("--output", help="Output path")

    args = parser.parse_args()
    device = connect(args)
    commands = {
        "info": info_command,
        "status": status_command,
        "watch": watch_command,
        "raw": raw_command,
        "methods": methods_command,
        "start": control_command,
        "stop": control_command,
        "dump": dump_command,
    }
    commands[args.command](device, args)


if __name__ == "__main__":
    main()
