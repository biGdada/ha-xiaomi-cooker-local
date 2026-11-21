# Xiaomi Rice Cooker — full local miIO integration for Home Assistant

A HACS custom component for `chunmi.cooker.*` rice cookers that talks **directly to the
device over the local miIO protocol**. Unlike the cloud-based Xiaomi integrations, it
exposes the raw cooker protocol: every status field, every setting bit, profiles,
temperature history and a raw-command escape hatch.

> ⚠️ This is a cooking appliance. Test commands with the cooker empty and watch it.
> The `raw_command` service can send anything the device understands.

## Why another integration?

The official Xiaomi/cloud integrations expose only a handful of cloud-mapped entities.
This one:

- polls `get_prop ["all"]` directly, so it sees fields the cloud never exposes
- keeps **raw values** alongside decoded ones, so new firmware/modes cannot break it
- exposes settings (LED, buzzer/warnings, keep-warm), interaction timeouts, appointments,
  stage/taste data and temperature history
- ships the upstream `python-miio` cooking profile library and accepts your own profiles
- includes **500+ Mi Home cloud recipes that run locally** on `normalcd1`, with photos,
  ingredients, steps, tips, bilingual search, local favorites and a HA language toggle
- includes a standalone probe so we can **map unknown fields together using the Mi Home app**

## Supported devices

### Confirmed working: `chunmi.cooker.normalcd1`

This is an ESP32/MIoT cooker (firmware 2.2.x) with a **24-value** raw status
payload, not the classic 12-field protocol. The integration auto-detects it and
uses named local reads (`status`, `cook_mode`, `temp`, `menu`, `version`,
`t_cook`) plus a dedicated raw parser. Local control is confirmed via the
legacy methods `start_cook [mode]` and `cancel_cooking []` — the standard MIoT
`action`/`set_properties` commands are not implemented on this firmware.
The cook mode select (1=Fine Cook, 2=Quick Cook, 3=Cook Congee, 4=Keep Warm)
feeds the Start button/service. The full Joyami/Mi Home recipe catalogue is bundled
and each recipe is rewritten locally into a runnable 133-byte `set_start` profile —
no cloud connection is needed to cook. See `MAPPING.md` for the full protocol notes.

### Classic protocol family (`python-miio` support list):

| Model | Notes |
| --- | --- |
| `chunmi.cooker.normal1` … `normal5` | Classic Mi IH rice cookers |
| `chunmi.cooker.press1`, `press2` | Pressure/IH cookers (different profile group) |
| `chunmi.cooker.eh1`, `chunmi.pre_cooker.eh1` | Detected if reported; profile group auto-selected |

Model is auto-detected on setup. If detection fails, enter it manually in the config
flow — you can find it with `tools/cooker_probe.py ... info`.

## Installation

### HACS (recommended)

1. HACS → Integrations → ⋮ → Custom repositories
2. Add `https://github.com/biGdada/ha-xiaomi-cooker-local` as **Integration**
3. Install **Xiaomi Rice Cooker (Local miio)**
4. Restart Home Assistant
5. Settings → Devices & Services → Add Integration → **Xiaomi Rice Cooker (Local miio)**

### Manual

Copy `custom_components/xiaomi_cooker_local` into your HA `config/custom_components/`
folder and restart HA.

## Getting the miIO token

The token is the 32-character device token used by Mi Home. Options:

- **Leave the token field empty in the config flow** — if another Xiaomi integration
  (`xiaomi_miio`, `Xiaomi Miot Auto`) already has this cooker at the same IP, the token
  is imported automatically from Home Assistant. This is local to your HA instance.
- Use the [Xiaomi Cloud Tokens Extractor](https://www.home-assistant.io/integrations/xiaomi_miio/#xiaomi-cloud-tokens-extractor)
- Or run `miiocli discover` / `miio discover` from `python-miio` on the same LAN
- Or use the probe tool below with a token obtained from a backup/rooted phone

The device cannot provide the token over local discovery alone; it is the encryption
key for the protocol. Cloud-account token retrieval is deliberately not part of this
integration's runtime.

The cooker must be on the same Layer-2 network as Home Assistant (no VLAN blocking
UDP port 54321).

## Configuration

The config flow asks for:

| Field | Description |
| --- | --- |
| IP address | Cooker's local IP |
| Token | 32 hex chars; leave empty to auto-import from another Xiaomi integration at the same IP |
| Name | Friendly name (default `Rice Cooker`) |
| Model | Optional — leave empty to auto-detect |
| Polling interval | Seconds, default 30 (min 5) |
| Connection timeout | Seconds, default 5 |

Options (reconfigure any time) let you change the polling interval, timeout, choose
the recipe source, and add your own profiles as JSON. Recipe source options:

- **Cache (first run and after updates)** — default. Uses the local catalogue and
  downloads it once on first install and once after each integration version update.
- **Every Home Assistant start** — downloads the catalogue on every restart.
- **Bundled JSON only** — never downloads automatically; use `Refresh recipes` manually.

The downloaded catalogue is stored in `.storage/xiaomi_cooker_local_recipes`, so normal
restarts do not hit the Joyami API.

```json
[
  {
    "title": "My sticky rice",
    "description": "Captured from Mi Home",
    "profile": "0001E1010000....81E9"
  }
]
```

## Entities

**Sensors** (raw variants are disabled by default):

`Mode`, `Mode code`, `Menu`, `Menu raw`, `Stage`, `Stage description`, `Stage code`,
`Stage raw`, `Rice ID`, `Taste`, `Taste phase`, `Temperature`, `Temperature raw`,
`Start time`, `Remaining`, `Delayed start`, `Duration`, `Favorite menu`,
`Favorite raw`, `Hardware version`, `Firmware version`, `Version raw`,
`Settings raw`, `Timeouts raw`, `Custom raw`, plus appointment sensors
(`Jingzhu appointment`, `Kuaizhu appointment`, `Zhuzhou appointment`,
`Favorite appointment`, `Favorite cooking`).

**Binary sensors:** `Cooking`, `Pressure supported`.

**Switches:** `Led On`, `Auto Keep Warm`, `Lid Open Warning`,
`Lid Open Warning Delayed`, `Jingzhu Auto Keep Warm`, `Kuaizhu Auto Keep Warm`,
`Zhuzhou Auto Keep Warm`, `Favorite Auto Keep Warm`.

**Numbers:** `Led Off`, `Lid Open`, `Lid Open Warning` (seconds).

**Select:** `Cooking profile` — remember which profile the start action uses.
On `normalcd1`: `Cook mode`. Recipe display language is controlled by the button on
the card, not by a separate entity.

**Sensors:** on `normalcd1`, `Recipe library` — the number of loaded recipes, with
attributes for the current language, last search, last viewed recipe and favorites —
plus `Recipe translation status` and `Recipe refresh status`. The refresh sensor reports
the current phase and `done`/`total` counts; every card reads it, so pressing Refresh on
one dashboard disables the button and shows the same progress on all other cards.

**Buttons:** `Start cooking`, `Stop cooking`, `Stop (legacy command)`,
`Acknowledge warnings`, `Disable warnings`, `Refresh state`.
On `normalcd1`: also `Refresh recipes` to redownload the catalogue from Joyami.

## Services

All services accept an optional `device_id` target (needed if you have more than one
cooker). Examples:

```yaml
# Start a built-in profile by name or by raw hex
action: xiaomi_cooker_local.start
data:
  device_id: abc123...
  profile: Jingzhu
```

```yaml
action: xiaomi_cooker_local.stop
```

```yaml
# Change several settings in one command
action: xiaomi_cooker_local.set_settings
data:
  led_on: true
  auto_keep_warm: false
  lid_open_warning: true
```

```yaml
action: xiaomi_cooker_local.set_timeouts
data:
  led_off: 5
  lid_open: 4
  lid_open_warning: 15
```

```yaml
# Protocol mapping: send anything
action: xiaomi_cooker_local.raw_command
data:
  method: get_prop
  parameters: ["all"]
```

```yaml
# Writes config/.storage/xiaomi_cooker_local_dump_<entry>_<timestamp>.json
# and returns the same data as the service response
action: xiaomi_cooker_local.dump
```

```yaml
action: xiaomi_cooker_local.get_temperature_history
response_variable: cooker_history
```

### Recipe services (on `normalcd1`)

```yaml
# Search in Chinese, English, or by ingredient
action: xiaomi_cooker_local.search_recipes
data:
  query: 温泉蛋
  limit: 10
response_variable: recipe_search
```

```yaml
# Full recipe: photo, ingredients, steps, tips, tools and runnable cookcode
action: xiaomi_cooker_local.get_recipe
data:
  recipe: 温泉蛋
response_variable: recipe
```

```yaml
# Start a cloud recipe locally (rewritten cookcode, no Xiaomi cloud)
action: xiaomi_cooker_local.start_recipe
data:
  recipe: 1823
```

```yaml
# Local HA favorites (unlimited; NOT the cooker's single 自选 slot)
action: xiaomi_cooker_local.add_favorite
data:
  recipe: 温泉蛋

action: xiaomi_cooker_local.remove_favorite
data:
  recipe: 温泉蛋

action: xiaomi_cooker_local.list_favorites
response_variable: favorites
```

Other recipe services: `refresh_recipes`. Core services: `set_menu`, `start`, `stop`.

## Recipe library and interface

On `chunmi.cooker.normalcd1` the integration ships the full Joyami recipe catalogue
(500+ recipes) with English text pre-translated in the bundled file. The in-plugin
`Refresh recipes` action and the card's **Translate recipe** button use Google's
public `translate.googleapis.com` endpoint (no API key) to translate any missing
strings for newly fetched recipes and cache them locally, so they remain in English
after a Home Assistant restart. If translation is unavailable or rate-limited, the
bundled translation or the original Chinese is used and the
`Recipe translation status` sensor shows a warning such as
`Translation service is rate-limited (HTTP 429)`. Local cooking control never depends
on it.

Language behaviour:

- The card starts in HA-language mode. Its **Language** button switches between
  HA's configured language and the original Chinese, then refreshes the open recipe
  and search results immediately.
- Only `en` and `zh` are bundled: non-Chinese HA languages display the English text,
  and Chinese HA displays the original Chinese.
- The button is labelled with HA's actual language name, for example
  `English (Home Assistant)`, not a generic "HA language" label.
- Search always scans both Chinese and English text, so it works in either mode.
- The Joyami API returns Chinese text only. After `refresh_recipes` or
  **Translate recipe**, translations are merged/cached locally so English display
  never disappears once translated.

A tailored **Xiaomi Rice Cooker** card is registered automatically with Home Assistant.
Open any dashboard, choose **Edit → Add Card**, and search for `Xiaomi Rice Cooker`.
The card shows cooker status, cook mode selection, start/stop controls, recipe search,
photos, ingredients, steps, tips, translation status and a live refresh progress bar.
The **Favorites** button lists
locally saved recipes and lets you open or remove them; a recipe's detail view has an
Add/Remove favorites button. Favorites are stored by Home Assistant and are separate
from the cooker's single `自选` slot. It binds to the native integration entities and
services automatically; if you have several cookers, set `device_id` in the card
configuration to choose one.

The JavaScript resource is served by the integration and added to Lovelace automatically
in storage mode. If you use Lovelace YAML mode, add this resource yourself:

```yaml
resources:
  - url: /xiaomi_cooker_local/xiaomi-cooker-card.js
    type: module
```

After updating, do a hard refresh in the browser (Ctrl/Cmd+F5) so the card picker picks
up the new resource. No helper entities or scripts are needed. The last search and last
opened recipe are exposed as attributes of the `Recipe library` sensor, so you can also
use them in your own Markdown or entity cards. A manual example remains in
[`lovelace/recipe_library.yaml`](lovelace/recipe_library.yaml) for reference.

Favorites are stored locally in HA (`.storage/xiaomi_cooker_local_favorites`), are
unlimited, and are completely separate from the cooker's single `自选` slot.

To regenerate the bundled catalogue from source:

```bash
pip install requests
python tools/build_recipe_bundle.py
```

## Mapping the device together (the important part)

Since the exact model/firmware is not known yet, the integration deliberately keeps raw
data. Use the standalone probe to discover what each Mi Home button does:

```bash
pip install python-miio==0.5.12

python tools/cooker_probe.py --host 192.168.1.50 --token TOKEN info
python tools/cooker_probe.py --host 192.168.1.50 --token TOKEN status
python tools/cooker_probe.py --host 192.168.1.50 --token TOKEN methods

# Watch mode: prints ONLY changed fields. Tap buttons in Mi Home and correlate.
python tools/cooker_probe.py --host 192.168.1.50 --token TOKEN \
  watch --interval 1 --log-file map.jsonl
```

`watch` writes every changed snapshot to `map.jsonl` as JSON lines. Send us that file
(with the token removed — the tool never logs it) plus:

1. the exact model string from `info`
2. what you tapped in the app and when
3. what the cooker physically did

Then we can turn unknown bytes into named entities and add newly discovered commands to
the component.

You can also call `xiaomi_cooker_local.dump` from HA while performing an action in the
app to capture a full before/after snapshot.

## Raw protocol reference

`get_prop ["all"]` returns 12 values in this order:

| # | Name | Meaning |
| --- | --- | --- |
| 0 | `func` | mode: `waiting`, `running`, `precook`, `autokeepwarm`, … |
| 1 | `menu` | selected menu id (hex) |
| 2 | `stage` | 10-char stage blob: state / rice id / taste / unknown |
| 3 | `temp` | idle temperature, or packed start-time data while cooking |
| 4 | `t_func` | remaining minutes |
| 5 | `t_precook` | delayed start in minutes (`-1` = none) |
| 6 | `t_cook` | total duration in minutes |
| 7 | `setting` | two-octet setting bitmask |
| 8 | `delay` | LED-off / lid-open / warning timeouts (hex seconds) |
| 9 | `version` | hardware + firmware version (hex) |
| 10 | `favorite` | favorite menu id (hex) |
| 11 | `custom` | appointment/customization blob |

`setting` bitmask:

- octet 0: bit0 pressure supported, bit1 LED, bit2 auto keep warm,
  bit3 lid warning, bit4 delayed lid warning
- octet 1: bit0 jingzhu, bit1 kuaizhu, bit2 zhuzhou, bit3 favorite auto keep warm

Known commands: `set_start [profile]`, `set_func ["end02"|"end"|"ack"|"nowarn"]`,
`set_menu [profile]`, `set_interaction [setting, led_off, lid_open, lid_warning]`,
`get_temp_history`, `get_prop ["all"]`.

## Troubleshooting

Enable debug logs:

```yaml
logger:
  logs:
    custom_components.xiaomi_cooker_local: debug
    miio: debug
```

Common issues:

- **Cannot connect** — wrong token, cooker offline, or UDP 54321 blocked.
- **Model unknown** — set it manually; some firmwares do not answer `miIO.info`.
- **State stops updating** — check HA logs; the coordinator marks entities unavailable
  and retries automatically.
- **Unknown stage name** — expected on new firmware. The raw value is still exposed;
  add it to `parsing.py` once we confirm the meaning.

## Development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

The parser, profile helpers and recipe helpers are pure Python and unit-tested without
Home Assistant.

## License

Apache-2.0. Cooking profile data originates from `python-miio` (GPL-3.0); see
`custom_components/xiaomi_cooker_local/profiles.json`.
