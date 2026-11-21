# Protocol mapping worksheet

## Confirmed device: `chunmi.cooker.normalcd1`

- hardware `esp32`, firmware `2.2.0_0010`, model reported by `miIO.info`
- **not** a classic 12-field cooker: `get_prop ["all"]` returns **24** values
- official MIoT spec: `urn:miot-spec-v2:device:cooker:0000A00B:chunmi-normalcd1:1`
  - status (siid 2 / piid 1): 1=Idle, 2=Running, 3=Keep Warm, 4=Cook Reservation
  - cook-mode: 1=Fine Cook, 2=Quick Cook, 3=Cook Congee, 4=Keep Warm
  - actions: start-cook (aiid 1, input [mode]), cancel-cooking (aiid 2)
- local named reads that work (one property per `get_prop` call):
  `status`, `cook_mode`, `temp`, `menu`, `version`, `t_cook`
- local writes that **work** (legacy methods, confirmed 2026-11-20):
  - `start_cook [mode]` → `[1]` (mode 1=Fine Cook, 2=Quick Cook,
    3=Cook Congee, 4=Keep Warm)
  - `cancel_cooking []` → `[1]` (stops cooking immediately)
  - `set_start [...]` → `[1]` but is a **no-op** on this firmware
- local writes that **fail** (device times out / `user ack timeout`):
  `get_properties`, `set_properties`, `set_prop`, `action`, `miot_action`,
  `call_action`, `set_status`, `set_func` (`ack`, `end`, `end02`, `stop`, ...)
  → standard MIoT commands are not implemented locally; use the legacy names above

### Decoding the 24 raw values

- values 4 and 5 are 8-byte blobs: `[seconds:uint32][unix_timestamp:uint32]`
  (the timestamp is the device's live clock)
- values 17 and 19 are Unix timestamps of the last cook's start/end
- value 3 is **remaining minutes**, not temperature (temperature comes from
  the named `temp` property)
- all values are exposed as `raw_00` … `raw_23` in the integration

### Field changes confirmed by driving the cooker (2026-11-20)

| Index | Field | Idle | Running (start) | Notes |
| --- | --- | --- | --- | --- |
| 00 | status / `func` | 1 | 2 | 1=Idle, 2=Running, 3=Keep Warm, 4=Reservation |
| 01 | `menu` | `0000000001` | `0100000002` | profile/menu id; mode 2 → `...0002` |
| 02 | `stage` | 11 / 0 | 0 → 2 | cooking stage; app start set 0, first stage 2 |
| 03 | `t_func` minutes | 60 | 40 | cook duration in minutes (named `temp` is actual °C) |
| 04 | `t_func` blob | seconds+clock | countdown+clock | first 4 bytes = remaining seconds |
| 07 | `setting` | 1 | 0 | run-state flag |
| 12 | (unknown) | 1 | 2 | tracks status code |
| 17 | raw timestamp | old date | start time | updated when cooking starts |
| 18 | run marker | 2 (idle) | 0 (running) | 2 seen after app stop |

Use the worksheet below to map the remaining bytes with the Mi Home app.

## Original worksheet

## 1. Identify the cooker

```bash
pip install python-miio==0.5.12

python tools/cooker_probe.py --host <IP> --token <TOKEN> info
```

Record:

| Item | Value |
| --- | --- |
| model | |
| hardware version | |
| firmware version | |
| device_id | |

If `info` fails but the cooker responds, try manually:
`python tools/cooker_probe.py --host <IP> --token <TOKEN> --model chunmi.cooker.normal2 status`

## 2. Capture the baseline

```bash
python tools/cooker_probe.py --host <IP> --token <TOKEN> status > baseline.txt
python tools/cooker_probe.py --host <IP> --token <TOKEN> methods > methods.txt
```

## 3. Watch changes while using Mi Home

```bash
python tools/cooker_probe.py --host <IP> --token <TOKEN> \
  watch --interval 1 --log-file map.jsonl
```

Leave it running. Then, one at a time:

1. Tap a button in Mi Home (e.g. "Start cooking", "Keep warm", "Timer", "Buzzer off").
2. Wait 3–5 seconds.
3. Note the wall-clock time and what you tapped in this table:

| Time (from watch output) | What I tapped in Mi Home | What the cooker did | Changed fields |
| --- | --- | --- | --- |
| | | | |

`map.jsonl` records every changed snapshot, so we can correlate exactly.

## 4. Extract a profile (optional)

If Mi Home lets you pick a recipe and the cooker accepts it, run:

```bash
python tools/cooker_probe.py --host <IP> --token <TOKEN> raw get_prop '["all"]'
```

A new `menu` value plus a changed `custom`/`setting` blob tells us which bits encode
the recipe. If the app sends a profile via `set_start`, capture it with a packet
capture or by watching HA debug logs after enabling:

```yaml
logger:
  logs:
    custom_components.xiaomi_cooker_local: debug
    miio: debug
```

## 5. Send us

- model / firmware / hardware from step 1
- `baseline.txt`, `methods.txt`, `map.jsonl`
- the filled-in table from step 3

The token is never written by the probe tool, but double-check before sharing.

## What we'll do next

With that data we can:

- name unknown `func` modes and `stage` states
- decode the remaining `custom` bytes (appointments)
- add newly discovered miIO commands as entities/services
- select the correct built-in profile group for your model
