"""Every entity of every fixture device, compared against a snapshot.

Run 'pytest tests/test_entities.py --snapshot-update' after a deliberate change and
review the diff of 'tests/__snapshots__/test_entities.ambr': a changed unique_id would
orphan the entity in every installation.
"""

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from syrupy.assertion import SnapshotAssertion

from .appliance import DEVICES, ApplianceNetwork
from .common import setup_appliance


@pytest.mark.parametrize("device", DEVICES)
async def test_entities(
    hass: HomeAssistant,
    appliances: ApplianceNetwork,
    freezer: FrozenDateTimeFactory,
    snapshot: SnapshotAssertion,
    device: str,
) -> None:
    freezer.move_to("2026-01-15 12:00:00+00:00")
    entry = await setup_appliance(hass, appliances.add(device))

    registry = er.async_get(hass)
    summary = {}
    for entity in sorted(
        er.async_entries_for_config_entry(registry, entry.entry_id),
        key=lambda e: e.unique_id,
    ):
        state = hass.states.get(entity.entity_id)
        summary[entity.unique_id] = {
            "entity_id": entity.entity_id,
            "translation_key": entity.translation_key,
            "original_name": entity.original_name,
            "entity_category": entity.entity_category,
            "disabled_by": entity.disabled_by,
            "device_class": entity.original_device_class,
            "icon": entity.original_icon,
            "unit": entity.unit_of_measurement,
            "state": state.state if state else None,
        }
    assert summary == snapshot


async def test_program_consumption_can_go_down(
    hass: HomeAssistant, appliances: ApplianceNetwork
) -> None:
    """The last program's consumption isn't a meter, it drops for a smaller program."""
    await setup_appliance(hass, appliances.add("adora_dish_v6000"))
    for entity_id in (
        "sensor.adora_sl_energy_program",
        "sensor.adora_sl_water_program",
    ):
        assert hass.states.get(entity_id).attributes["state_class"] == "total"
