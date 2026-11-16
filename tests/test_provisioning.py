"""Wi-Fi provisioning over Bluetooth, against a fake appliance."""

import pytest

from custom_components.vzug.api import provisioning


class FakeAppliance:
    """Answers like an appliance: joins the network and reports its address."""

    def __init__(self, states=((1, 0), (2, 0))):
        self.states = states
        self.address = bytes([0, 0, 0, 0, 0])
        self.written: list[bytes] = []
        self.callback = None

    async def pair(self):
        raise NotImplementedError

    async def read_gatt_char(self, char):
        assert char == provisioning.CHAR_NETWORK_CONFIGURATION
        return self.address

    async def start_notify(self, char, callback):
        assert char == provisioning.CHAR_CONNECTION_STATE
        self.callback = callback

    async def stop_notify(self, char):
        pass

    async def write_gatt_char(self, char, data, response):
        assert char == provisioning.CHAR_CONFIGURE_WLAN and response
        self.written.append(bytes(data))
        for state in self.states:
            self.callback(None, bytearray(state))
        if self.states[-1][0] == provisioning.STATE_CONNECTED:
            self.address = bytes([1, 192, 168, 1, 57])


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr(provisioning, "ADDRESS_DELAY", 0)


def test_serial_and_payloads():
    assert provisioning.serial_from_manufacturer_data(b"21045 006312") == "21045 006312"
    assert provisioning.serial_from_manufacturer_data(b"\xff\x00") is None
    assert provisioning.encode_wlan("Home", "secret") == b"\x00\x04Home\x06secret"
    assert provisioning.decode_ip(bytes([3, 10, 0, 0, 7, 9])) == "10.0.0.7"
    assert provisioning.decode_ip(bytes(5)) is None


@pytest.mark.asyncio
async def test_provision_returns_the_new_address():
    appliance = FakeAppliance()
    assert await provisioning.provision(appliance, "Home", "secret") == "192.168.1.57"
    assert appliance.written == [b"\x00\x04Home\x06secret"]


@pytest.mark.asyncio
async def test_wrong_password():
    appliance = FakeAppliance(states=((0, provisioning.ERROR_INVALID_PSK),))
    with pytest.raises(provisioning.WrongCredentials):
        await provisioning.provision(appliance, "Home", "wrong")


def test_bluetooth_stays_optional():
    """Appliances on the LAN must work on a Home Assistant without Bluetooth."""
    import json
    import pathlib

    manifest = json.loads(
        (pathlib.Path(provisioning.__file__).parents[1] / "manifest.json").read_text()
    )
    assert not {"bluetooth", "bluetooth_adapters"} & set(manifest["dependencies"])
    assert "bluetooth_adapters" in manifest["after_dependencies"]
    assert {"manufacturer_id": 0x05CE, "connectable": True} in manifest["bluetooth"]
