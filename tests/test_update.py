from unittest.mock import MagicMock

import pytest
from homeassistant.const import STATE_OFF, STATE_ON

from custom_components.vzug.api import AggUpdateStatus
from custom_components.vzug.update import VZugUpdate


def _data(
    ai: str | None = "1052633-R19",
    hh: str | None = "1044431-R32",
    *,
    ai_update: bool = False,
    hhg_update: bool = False,
) -> AggUpdateStatus:
    return AggUpdateStatus(
        update={
            "status": "idle",
            "isAIUpdateAvailable": ai_update,
            "isHHGUpdateAvailable": hhg_update,
        },
        ai_fw_version={"SW": ai} if ai else {},
        hh_fw_version={"v": hh} if hh else {},
    )


def _entity(data: AggUpdateStatus) -> VZugUpdate:
    shared = MagicMock()
    shared.unique_id_prefix = "fc:1b:ff:00:00:00"
    shared.device_info = {}
    shared.update_coord.data = data
    entity = VZugUpdate(shared)
    entity.async_write_ha_state = MagicMock()
    return entity


def _write(entity: VZugUpdate, data: AggUpdateStatus) -> str | None:
    """Poll and evaluate the entity in the order HA does when writing the state.

    'state_attributes' is where HA releases a skip, so it has to run too.
    """
    entity.coordinator.data = data
    state = entity.state
    entity.state_attributes
    return state


def test_no_update():
    entity = _entity(_data())

    assert entity.latest_version == "1052633-R19"
    assert _write(entity, _data()) == STATE_OFF


@pytest.mark.parametrize(
    ("data", "latest"),
    [
        (_data(ai_update=True), "newer than 1052633-R19"),
        (_data(hhg_update=True), "newer than 1044431-R32"),
        (
            _data(ai_update=True, hhg_update=True),
            "newer than 1052633-R19, 1044431-R32",
        ),
        (_data(hh=None, hhg_update=True), None),
    ],
    ids=["ai", "hhg", "both", "hh-read-failed"],
)
def test_available_update(data, latest):
    entity = _entity(data)

    assert entity.latest_version == latest
    if latest is not None:
        assert _write(entity, data) == STATE_ON


def test_unknown_installed_version():
    entity = _entity(_data(ai=None, ai_update=True))

    assert entity.latest_version is None
    assert entity.state is None


@pytest.mark.asyncio
async def test_skip_ends_with_the_next_firmware():
    """The next update may be pending before any poll has seen 'no update'."""
    entity = _entity(_data(ai_update=True))
    await entity.async_skip()
    assert _write(entity, _data(ai_update=True)) == STATE_OFF

    # R20 got installed and the appliance already reports the next update
    assert _write(entity, _data("1052633-R20", ai_update=True)) == STATE_ON


@pytest.mark.asyncio
async def test_skipped_hhg_update_does_not_hide_an_ai_update():
    entity = _entity(_data(hhg_update=True))
    await entity.async_skip()

    assert _write(entity, _data(ai_update=True, hhg_update=True)) == STATE_ON


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failed",
    [
        pytest.param(_data(ai=None, ai_update=True), id="ai-fw-version"),
        pytest.param(_data(hh=None, hhg_update=True), id="hh-fw-version"),
    ],
)
async def test_failed_version_read_keeps_the_skip(failed):
    """'default_on_error' turns a failed request into an empty response."""
    good = _data(ai_update=True, hhg_update=True)
    entity = _entity(good)
    await entity.async_skip()

    _write(entity, failed)

    assert _write(entity, good) == STATE_OFF
