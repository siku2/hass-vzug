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
    instance.client = MagicMock()
    instance.state_coord = MagicMock()
    instance.state_coord.data = None
    instance._first_refresh_done = True
    instance._eco_stale_count = 0
    return instance


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
