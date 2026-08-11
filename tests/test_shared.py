from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.vzug.api import AggState
from custom_components.vzug.shared import STATE_MAX_STALE_UPDATES, Shared

_ECO_INFO = {"water": {"total": 80085.5}, "energy": {"total": 615.7}}


@pytest.fixture
def shared():
    """A Shared instance without the HomeAssistant machinery around it."""
    instance = Shared.__new__(Shared)
    instance.hass = MagicMock()
    instance.client = MagicMock()
    instance.config_coord = MagicMock()
    instance.state_coord = MagicMock()
    instance.state_coord.data = None
    instance._first_refresh_done = True
    instance._eco_stale_count = 0
    instance._device_active = None
    return instance


def _config_refreshes(shared: Shared) -> int:
    return shared.hass.async_create_task.call_count


def _state(eco_info):
    return AggState(
        zh_mode=2,
        device={"Inactive": "true"},
        device_fetched_at=datetime(2026, 8, 11, 12, 0, tzinfo=UTC),
        notifications=[],
        eco_info=eco_info,
    )


async def _poll(shared: Shared, eco_info) -> AggState:
    """Run one update and store the result the way the coordinator would."""
    shared.client.aggregate_state = AsyncMock(return_value=_state(eco_info))
    state = await shared._fetch_state()
    shared.state_coord.data = state
    return state


@pytest.mark.asyncio
async def test_zeroed_eco_info_keeps_the_previous_values(shared):
    """An all-zero response would otherwise put every eco sensor to 'unknown'."""
    await _poll(shared, _ECO_INFO)

    state = await _poll(shared, {})

    assert state.eco_info == _ECO_INFO


@pytest.mark.asyncio
async def test_a_real_response_resets_the_grace_period(shared):
    await _poll(shared, _ECO_INFO)
    await _poll(shared, {})
    assert shared._eco_stale_count == 1

    await _poll(shared, _ECO_INFO)

    assert shared._eco_stale_count == 0


@pytest.mark.asyncio
async def test_the_grace_period_is_bounded(shared):
    """'ecomXstatXtotalXclear' resets the counters, that has to reach the sensors."""
    await _poll(shared, _ECO_INFO)

    for _ in range(STATE_MAX_STALE_UPDATES):
        assert (await _poll(shared, {})).eco_info == _ECO_INFO

    assert (await _poll(shared, {})).eco_info == {}


@pytest.mark.asyncio
async def test_without_previous_values_there_is_nothing_to_keep(shared):
    """The very first update has no history to fall back on."""
    state = await _poll(shared, {})

    assert state.eco_info == {}
    assert shared._eco_stale_count == 0


def test_first_state_does_not_refresh_config(shared):
    """Nothing to compare against yet, so there is nothing to react to."""
    shared._track_activity({"Inactive": "true"})

    assert shared._device_active is False
    assert _config_refreshes(shared) == 0


def test_program_start_refreshes_config(shared):
    shared._track_activity({"Inactive": "true"})
    shared._track_activity({"Inactive": "false"})

    assert shared._device_active is True
    assert _config_refreshes(shared) == 1


def test_program_end_refreshes_config(shared):
    """The eco statistics in the config tree are updated on completion."""
    shared._track_activity({"Inactive": "false"})
    shared._track_activity({"Inactive": "true"})

    assert _config_refreshes(shared) == 1


def test_unchanged_activity_does_not_refresh_config(shared):
    for _ in range(5):
        shared._track_activity({"Inactive": "true"})

    assert _config_refreshes(shared) == 0


def test_unknown_activity_is_ignored(shared):
    """An appliance which doesn't report 'Inactive' must not trigger anything."""
    shared._track_activity({"Inactive": "false"})
    shared._track_activity({})
    shared._track_activity({"Inactive": "maybe"})

    # the last known state is kept, so a later 'true' still counts as a change
    assert shared._device_active is True
    assert _config_refreshes(shared) == 0

    shared._track_activity({"Inactive": "true"})
    assert _config_refreshes(shared) == 1
