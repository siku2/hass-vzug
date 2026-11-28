"""Zones and programs, as appliances report them through 'getProgram'.

Refrigerators answer 'getProgram' with one entry per zone, dishwashers with the
selected or running program (or just {"status":"idle"}).

Everything here is plain data in, plain data out, so it can be tested without
Home Assistant. The coordinator in 'shared.py' fills a 'ZoneState', the entities
only read from it and write through 'api.VZugApi.set_zone_value' /
'api.VZugApi.set_cmd_value'.
"""

import dataclasses
import json
import pathlib
import re
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

# functions that run for a while and then switch themselves off. The value is the
# duration in seconds, "0" stops them early.
BOOST_KEYS: tuple[str, ...] = ("superCool", "superFreeze")
# PartyCooling covers the whole appliance: setting it on one zone sets every zone.
PARTY_KEY = "partyCooling"
TEMP_KEY = "temp"
DOOR_KEY = "doorClosed"
# the kitchen timer is a zone of its own ('countdown1'), its value is 'duration'
TIMER_KEY = "duration"

# 'cmd' settings outside the category tree, read with 'getcmd<name>'
SWITCH_MODES: tuple[str, ...] = ("HolidayMode", "SilentPlusMode", "MonoFridgeMode")
SENSOR_MODES: tuple[str, ...] = ("SabbatMode",)
UNIT_MODE = "TemperatureUnit"
# wine cabinets: interior light, '0' (off) to '5'
ILLUMINATION_MODE = "Illumination"
ALL_MODES: tuple[str, ...] = (
    *SWITCH_MODES,
    *SENSOR_MODES,
    UNIT_MODE,
    ILLUMINATION_MODE,
)

Zone = Mapping[str, Any]

# program id -> {"key": translation key, "description": {"en": ..., ...}}, from the
# V-ZUG app's program names. Loaded on import, which Home Assistant runs in an
# executor.
PROGRAMS: dict[str, dict[str, Any]] = json.loads(
    pathlib.Path(__file__).with_name("programs.json").read_text(encoding="utf-8")
)


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ZoneState:
    zones: Mapping[str, Zone]
    """'getProgram' entries keyed by their zone name"""
    modes: Mapping[str, str]
    """raw answers to 'getcmd<name>' for the modes this appliance supports"""
    fetched_at: datetime = dataclasses.field(default_factory=dt_util.utcnow)
    """times in 'getProgram' are seconds from this moment"""


def index_zones(raw_programs: Iterable[Mapping[str, Any]]) -> dict[str, Zone]:
    """Key the 'getProgram' entries by zone name, dropping entries without one."""
    return {
        program["zone"]: program
        for program in raw_programs
        if isinstance(program.get("zone"), str)
    }


def has_zones(raw_programs: Iterable[Mapping[str, Any]]) -> bool:
    return bool(index_zones(raw_programs))


def zones_with(zones: Mapping[str, Zone], key: str) -> list[str]:
    """Names of the zones that offer 'key', in the order the appliance lists them."""
    return [name for name, zone in zones.items() if isinstance(zone.get(key), Mapping)]


def is_timer_zone(name: str) -> bool:
    return name.startswith("countdown")


COOLING_ZONES = ("fridge", "freezer")
WARMING_DRAWER_PROGRAM = 103
TIMER_PROGRAM = 9000


def is_cooling_zone(name: str) -> bool:
    return name.rstrip("0123456789") in COOLING_ZONES


def is_program_zone(name: str) -> bool:
    """Zones running programs with a state and an end (ovens, drawers, hobs).

    A fridge zone is always 'active' and never ends, the timer has its own entities.
    """
    return not is_timer_zone(name) and not is_cooling_zone(name)


def is_oven_zone(name: str, zone: Zone) -> bool:
    """The cooking chamber of an oven or steamer, ex. 'cookingChamber1'."""
    return name.startswith("cookingChamber") or any(
        key in zone for key in ("doorStatus", "preheatStatus", "probeInserted")
    )


def is_warming_drawer(name: str) -> bool:
    return name.startswith("warmingDrawer")


def is_hob_zone(name: str) -> bool:
    """Hob cooking zones are numbered '1', '2', ... (shown as A, B, ...)."""
    return name.isdigit()


def hob_zone_letter(name: str) -> str:
    return chr(64 + int(name)) if name.isdigit() and 0 < int(name) < 27 else name


def pan_detected(zone: Zone | None) -> bool | None:
    """The hob reports where a pan stands ('xc', 'yc') and its size."""
    if zone is None:
        return None
    return zone.get("xc") is not None and zone.get("yc") is not None


# options and readings of the selected program, by appliance type
PROGRAM_FLAGS = {
    "GS": (
        "energySaving",
        "partialload",
        "optiStart",
        "steamfinish",
        "rinsePlus",
        "dryPlus",
    ),
    "WA": ("addWash",),
}
PROGRAM_VALUES = {
    "WA": ("fillLevelA", "fillLevelB", "optidosLevelA", "optidosLevelB"),
}


def value(zone: Zone | None, key: str) -> Any:
    """'act' of a parameter, else 'set'."""
    if not zone:
        return None
    param = zone.get(key)
    if isinstance(param, Mapping):
        return param.get("act", param.get("set"))
    return param


def flag(zone: Zone | None, key: str) -> bool | None:
    """An on/off value: {"set":false,"options":[...]} or {"act":false}, the
    appliance's 'act' wins over the requested 'set'."""
    if not zone:
        return None
    value = zone.get(key)
    if isinstance(value, Mapping):
        value = value.get("act", value.get("set"))
    return value if isinstance(value, bool) else None


def can_toggle(zone: Zone | None, key: str) -> bool:
    options = value_field(zone, key, "options")
    return isinstance(options, list) and True in options and False in options


def value_field(zone: Zone | None, key: str, field: str) -> Any:
    """ex. value_field(zone, "temp", "set") -> 6.0, None when missing."""
    if not zone:
        return None
    value = zone.get(key)
    if not isinstance(value, Mapping):
        return None
    return value.get(field)


def is_running(zone: Zone | None, key: str) -> bool:
    """A timed function runs while the appliance reports how long it was set for."""
    seconds = value_field(zone, key, "set")
    return isinstance(seconds, (int, float)) and seconds > 0


def remaining_seconds(zone: Zone | None, key: str) -> int | None:
    if not is_running(zone, key):
        return None
    left = value_field(zone, key, "act")
    if not isinstance(left, (int, float)):
        return None
    return max(int(left), 0)


def format_value(value: float) -> str:
    """The appliance wants strings, and integral values without a trailing '.0'."""
    return str(int(value)) if float(value).is_integer() else str(value)


def mode_is_on(raw: str | None) -> bool | None:
    """'true' / 'false' for the switches, a number of hours ('0' = off) for Sabbath."""
    if raw is None:
        return None
    lowered = raw.strip().lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    try:
        return float(lowered) > 0
    except ValueError:
        return None


PROGRAM_STATES = ("active", "paused", "timed", "selected", "idle", "locked")


def _seconds(zone: Zone | None, key: str, field: str) -> float | None:
    value = value_field(zone, key, field)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    return float(value)


def end_time(zone: Zone | None, fetched_at: datetime) -> datetime | None:
    """When the program ends. 'getProgram' reports seconds from now: 'endtime',
    or failing that, while running, the remaining 'duration'."""
    seconds = _seconds(zone, "endtime", "act") or _seconds(zone, "endtime", "set")
    if seconds is None and zone and zone.get("status") == "active":
        seconds = _seconds(zone, TIMER_KEY, "act")
    return None if seconds is None else fetched_at + timedelta(seconds=seconds)


def start_time(zone: Zone | None, fetched_at: datetime) -> datetime | None:
    """When a delayed program starts ('timed' status, seconds from now)."""
    seconds = _seconds(zone, START_DELAY_KEY, "act") or _seconds(
        zone, START_DELAY_KEY, "set"
    )
    return None if seconds is None else fetched_at + timedelta(seconds=seconds)


def temperature_unit(modes: Mapping[str, str]) -> str:
    return "°F" if "F" in modes.get(UNIT_MODE, "") else "°C"


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ProgramState:
    names: Mapping[int, str]
    """program id -> name, in the order the appliance lists them"""
    current: Mapping[str, Any] | None
    """the selected or running program, None while idle"""
    fetched_at: datetime = dataclasses.field(default_factory=dt_util.utcnow)
    """times in 'getProgram' are seconds from this moment"""


def current_program(
    raw_programs: Iterable[Mapping[str, Any]], zone: str | None = None
) -> Mapping[str, Any] | None:
    """The selected or running program; for ovens, the one in 'zone'."""
    for program in raw_programs:
        if zone is not None and program.get("zone") != zone:
            continue
        if isinstance(program.get("id"), int) and program.get("status") != "idle":
            return program
    return None


# what an oven program can be sent with, besides its on/off options
PROGRAM_SETTINGS = ("temp", "duration")


def program_settings(
    program: Mapping[str, Any] | None, wanted: Mapping[str, float]
) -> dict[str, int]:
    """The temperature (°C) and duration (s) to send with an oven program.

    Like the V-ZUG app, a value outside the program's min / max is left out and
    the appliance keeps its own.
    """
    settings: dict[str, int] = {}
    for key, value in wanted.items():
        low = value_field(program, key, "min")
        high = value_field(program, key, "max")
        if value and low is not None and high is not None and low <= value <= high:
            settings[key] = int(value)
    return settings


def program_key(name: str) -> str:
    """'Fondue/Raclette' -> 'fondue_raclette', the select option for a program.

    Options are translation keys so Home Assistant can show each program with its
    own name and icon. A program we have no translation for shows its key.
    """
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def program_id_by_key(names: Mapping[int, str], key: str) -> int | None:
    return next((pid for pid, name in names.items() if program_key(name) == key), None)


def program_options(program: Mapping[str, Any]) -> dict[str, bool]:
    """The on/off options of a selected program, as 'Send to appliance' sends them.

    Recorded from the V-ZUG app for Eco:
    {"id":50,"dryPlus":false,"energySaving":false,"partialload":false,"rinsePlus":false}
    Only options the appliance lets you change (those listing 'options') are sent.
    """
    return {
        key: bool(value.get("set", False))
        for key, value in program.items()
        if isinstance(value, Mapping) and can_toggle(program, key)
    }


START_DELAY_KEY = "starttime"


def start_delay_seconds(program: Mapping[str, Any] | None, hours: float) -> int | None:
    """The 'starttime' to send with a program for a delayed start, or None.

    A selected dishwasher program offers it as {"min":0,"max":86400,"step":600}
    (seconds). The delay is rounded to the step and kept within min and max.
    """
    if not program or hours <= 0:
        return None
    limits = program.get(START_DELAY_KEY)
    if not isinstance(limits, Mapping):
        return None
    low = int(limits.get("min", 0) or 0)
    high = int(limits.get("max", 0) or 0)
    step = int(limits.get("step", 1) or 1)
    seconds = round(hours * 3600 / step) * step
    seconds = max(low, min(high, seconds))
    return seconds or None


def start_delay_max_hours(program: Mapping[str, Any] | None) -> float:
    """The longest delay the selected program allows, 24 h when unknown."""
    limits = program.get(START_DELAY_KEY) if program else None
    if isinstance(limits, Mapping) and isinstance(limits.get("max"), (int, float)):
        return float(limits["max"]) / 3600
    return 24.0
