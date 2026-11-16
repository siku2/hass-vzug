"""Put a new appliance on Wi-Fi over Bluetooth LE, like the V-ZUG app does.

The appliance must have V-ZUG-Home switched on in its user settings, then it
advertises manufacturer data 0x05CE followed by its serial number. Reading the
network configuration triggers bonding; the Wi-Fi credentials are written in
plain text over the bonded (encrypted) link, and the appliance reports its new
IP address afterwards. Nothing involves the V-ZUG cloud.
"""

import asyncio
import contextlib
import ipaddress
import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

MANUFACTURER_ID = 0x05CE

CHAR_CONFIGURE_WLAN = "aaaa1413-1211-1009-0807-06050403ff03"
CHAR_CONNECTION_STATE = "aaaa1413-1211-1009-0807-06050403ff04"
CHAR_NETWORK_CONFIGURATION = "aaaa1413-1211-1009-0807-06050403ff06"

STATE_CONNECTED = 2
ERROR_INVALID_SSID = 1
ERROR_INVALID_PSK = 2

# how long the app waits for the appliance to join, and to get its address
CONNECT_TIMEOUT = 60.0
ADDRESS_DELAY = 5.0


class ProvisioningError(Exception): ...


class WrongCredentials(ProvisioningError):
    """The appliance couldn't find the network or the password is wrong."""


def serial_from_manufacturer_data(data: bytes | None) -> str | None:
    """b"21045 006312" -> "21045 006312", None if it isn't a serial number."""
    if not data:
        return None
    try:
        serial = data.decode().strip()
    except UnicodeDecodeError:
        return None
    model, _, number = serial.partition(" ")
    return serial if model.isalnum() and number.isdigit() else None


def encode_wlan(ssid: str, password: str) -> bytes:
    """00 | len(ssid) | ssid | len(psk) | psk"""
    ssid_raw, psk_raw = ssid.encode(), password.encode()
    if len(ssid_raw) > 255 or len(psk_raw) > 255:
        raise WrongCredentials("SSID or password too long")
    return b"\x00" + bytes([len(ssid_raw)]) + ssid_raw + bytes([len(psk_raw)]) + psk_raw


def decode_ip(data: bytes) -> str | None:
    """Network configuration: [?][ip0][ip1][ip2][ip3]..., None while not on Wi-Fi."""
    if len(data) < 5:
        raise ProvisioningError(f"invalid network configuration: {data.hex()}")
    address = ipaddress.IPv4Address(bytes(data[1:5]))
    return None if address.is_unspecified else str(address)


async def provision(client: Any, ssid: str, password: str) -> str:
    """Send the Wi-Fi credentials to a connected appliance, return its new IP.

    'client' is a connected 'bleak.BleakClient'.
    """
    # bonding: the first read of the network configuration is protected
    try:
        await client.pair()
    except Exception as exc:  # not every backend needs (or supports) it
        _LOGGER.debug("explicit pairing failed, relying on the read: %r", exc)
    _LOGGER.debug(
        "current address: %s",
        decode_ip(await client.read_gatt_char(CHAR_NETWORK_CONFIGURATION)),
    )

    result: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    def on_state(_: Any, data: bytearray) -> None:
        if result.done() or len(data) < 2:
            return
        state, error = data[0], data[1]
        _LOGGER.debug("connection state %s, error %s", state, error)
        if state == STATE_CONNECTED:
            result.set_result(None)
        elif error in (ERROR_INVALID_SSID, ERROR_INVALID_PSK):
            result.set_exception(WrongCredentials(f"error {error}"))
        elif error:
            result.set_exception(
                ProvisioningError(f"network configuration failed: {error}")
            )

    await client.start_notify(CHAR_CONNECTION_STATE, on_state)
    try:
        await client.write_gatt_char(
            CHAR_CONFIGURE_WLAN, encode_wlan(ssid, password), response=True
        )
        async with asyncio.timeout(CONNECT_TIMEOUT):
            await result
    except TimeoutError as exc:
        raise ProvisioningError(
            "the appliance didn't join the network in time"
        ) from exc
    finally:
        # the appliance may drop the link once it is on Wi-Fi
        with contextlib.suppress(Exception):
            await client.stop_notify(CHAR_CONNECTION_STATE)

    await asyncio.sleep(ADDRESS_DELAY)
    address = decode_ip(await client.read_gatt_char(CHAR_NETWORK_CONFIGURATION))
    if address is None:
        raise ProvisioningError("the appliance joined but reports no address")
    return address
