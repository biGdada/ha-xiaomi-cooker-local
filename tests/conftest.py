"""Test setup: stub the package path so pure-python modules import without HA."""

from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

for name, path in (
    ("custom_components", ROOT / "custom_components"),
    (
        "custom_components.xiaomi_cooker_local",
        ROOT / "custom_components" / "xiaomi_cooker_local",
    ),
):
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        module.__path__ = [str(path)]
        sys.modules[name] = module
