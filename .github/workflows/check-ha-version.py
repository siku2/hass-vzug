#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# ///
import json
import sys
import tomllib
from pathlib import Path

hacs = json.loads(Path("hacs.json").read_text())["homeassistant"]
lock = tomllib.loads(Path("uv.lock").read_text())
locked = next(p["version"] for p in lock["package"] if p["name"] == "homeassistant")

if hacs != locked:
    print(
        f"::error file=hacs.json::hacs.json requires Home Assistant {hacs}, but uv.lock has {locked}"
    )
    sys.exit(1)
