import asyncio
import contextlib
import dataclasses
import logging
from collections.abc import AsyncIterator
from ipaddress import IPv4Interface
from typing import Any

_LOGGER = logging.getLogger(__name__)


_PORT = 2047
_PING = b"DISCOVERY_LAN_INTERFACE_REQUEST"
_PONG = b"DISCOVERY_LAN_INTERFACE_RESPONSE"


@dataclasses.dataclass(slots=True, kw_only=True)
class DiscoveryInfo:
    host: str


class _DiscoveryProtocol(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.discoveries: asyncio.Queue[DiscoveryInfo | None] = asyncio.Queue()

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        _LOGGER.debug("connection made")

    def connection_lost(self, exc: Exception | None) -> None:
        _LOGGER.debug("connection lost: %s", exc)
        self.discoveries.put_nowait(None)

    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]) -> None:
        if not data.startswith(_PONG):
            return

        _LOGGER.debug("received response from %s: %s", addr, data)
        self.discoveries.put_nowait(
            DiscoveryInfo(
                host=str(addr[0]),
            )
        )

    def error_received(self, exc: Exception) -> None:
        _LOGGER.warn("received error", exc_info=exc)


async def _make_iter(protocol: _DiscoveryProtocol) -> AsyncIterator[DiscoveryInfo]:
    while True:
        discovery = await protocol.discoveries.get()
        if discovery is None:
            break
        yield discovery


@contextlib.asynccontextmanager
async def create_discovery_stream(interface: IPv4Interface, timeout: float | None):
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        _DiscoveryProtocol,
        local_addr=(str(interface.ip), _PORT),
        allow_broadcast=True,
    )
    try:
        transport.sendto(
            _PING,
            (str(interface.network.broadcast_address), _PORT),
        )
        if timeout:
            loop.call_later(timeout, lambda: transport.close())

        yield _make_iter(protocol)
    finally:
        transport.abort()


async def discover_list(
    interface: IPv4Interface, timeout: float
) -> list[DiscoveryInfo]:
    collected: list[DiscoveryInfo] = []
    async with create_discovery_stream(interface, timeout) as stream:
        async for discovery in stream:
            collected.append(discovery)
    return collected
