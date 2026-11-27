from collections.abc import Iterator
from unittest.mock import patch

# Home Assistant 2026.11 aliases httpx and httpcore to httpx2 and httpcore2 on
# import. Import it before any test module imports httpx, like HA does at runtime.
import homeassistant  # noqa: F401
import httpx
import pytest

from custom_components.vzug import api
from custom_components.vzug.api import provisioning

from .appliance import ApplianceNetwork


@pytest.fixture(autouse=True)
def _no_retry_delays(monkeypatch: pytest.MonkeyPatch) -> None:
    """The API waits between retries, tests don't have to."""
    monkeypatch.setattr(api, "RETRY_DELAY", 0.0)
    monkeypatch.setattr(api, "EMPTY_CATEGORIES_RETRY_DELAYS", (0.0, 0.0))
    monkeypatch.setattr(provisioning, "ADDRESS_DELAY", 0.0)


@pytest.fixture
def appliances() -> Iterator[ApplianceNetwork]:
    """Simulated appliances; every VZugApi talks to them instead of the network."""
    network = ApplianceNetwork()

    def create_client(self: api.VZugApi) -> httpx.AsyncClient:
        return httpx.AsyncClient(auth=self._auth, transport=network.transport())

    with patch.object(api.VZugApi, "_create_client", create_client):
        yield network
