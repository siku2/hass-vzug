"""Finding appliances on the network with the V-ZUG UDP broadcast."""

import asyncio
from ipaddress import IPv4Interface

import pytest

from custom_components.vzug.api import discovery


class FakeTransport:
    def __init__(self) -> None:
        self.sent: list[tuple[bytes, tuple[str, int]]] = []
        self.aborted = False
        self.closed = False

    def sendto(self, data: bytes, addr: tuple[str, int]) -> None:
        self.sent.append((data, addr))

    def close(self) -> None:
        self.closed = True

    def abort(self) -> None:
        self.aborted = True


@pytest.fixture
async def endpoint(monkeypatch: pytest.MonkeyPatch):
    """Replace the UDP socket: answer the broadcast like two appliances would."""
    state = {}

    async def create_datagram_endpoint(factory, **kwargs):
        protocol = factory()
        transport = FakeTransport()
        state.update(protocol=protocol, transport=transport, kwargs=kwargs)
        protocol.connection_made(transport)
        loop = asyncio.get_running_loop()
        loop.call_soon(
            protocol.datagram_received,
            discovery._PONG + b"something",
            ("192.0.2.20", discovery._PORT),
        )
        loop.call_soon(protocol.datagram_received, b"noise", ("192.0.2.30", 1))
        loop.call_soon(
            protocol.datagram_received, discovery._PONG, ("192.0.2.21", 2047)
        )
        loop.call_soon(protocol.error_received, OSError("ignored"))
        loop.call_soon(protocol.connection_lost, None)
        return transport, protocol

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "create_datagram_endpoint", create_datagram_endpoint)
    return state


async def test_discover_list(endpoint) -> None:
    found = await discovery.discover_list(IPv4Interface("192.0.2.10/24"), timeout=1)

    assert found == [
        discovery.DiscoveryInfo(host="192.0.2.20"),
        discovery.DiscoveryInfo(host="192.0.2.21"),
    ]
    assert endpoint["kwargs"] == {
        "local_addr": ("192.0.2.10", discovery._PORT),
        "allow_broadcast": True,
    }
    transport = endpoint["transport"]
    assert transport.sent == [(discovery._PING, ("192.0.2.255", discovery._PORT))]
    assert transport.aborted


async def test_discovery_stops_after_the_timeout(monkeypatch) -> None:
    transport = FakeTransport()

    async def create_datagram_endpoint(factory, **kwargs):
        protocol = factory()

        def close() -> None:
            transport.closed = True
            protocol.connection_lost(None)

        transport.close = close
        return transport, protocol

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "create_datagram_endpoint", create_datagram_endpoint)
    found = await discovery.discover_list(IPv4Interface("192.0.2.10/24"), timeout=0.01)
    assert found == []
    assert transport.closed
