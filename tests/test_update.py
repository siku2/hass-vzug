from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.vzug.api import AggUpdateStatus
from custom_components.vzug.update import VZugUpdate


def _entity(component: str) -> VZugUpdate:
    shared = MagicMock()
    shared.unique_id_prefix = "fc:1b:ff:00:00:00"
    shared.device_info = {}
    shared.client.do_ai_update = AsyncMock()
    shared.client.do_hhg_update = AsyncMock()
    shared.update_coord.data = AggUpdateStatus(
        update={
            "status": "idle",
            "components": [{"name": component, "available": True}],
        },
        ai_fw_version={"SW": "1052633-R19"},
        hh_fw_version={},
    )
    shared.update_coord.async_request_refresh = AsyncMock()
    return VZugUpdate(shared)


@pytest.mark.asyncio
@pytest.mark.parametrize("component", ["AI", "HHG"])
async def test_install_starts_watching_before_the_refresh(component):
    """The status may still read 'idle' when the refresh right after it runs."""
    entity = _entity(component)
    shared = entity.shared
    shared.update_coord.async_request_refresh.side_effect = lambda: (
        shared.note_update_activity.assert_called_once()
    )

    await entity.async_install(None, False)

    shared.update_coord.async_request_refresh.assert_awaited_once()
