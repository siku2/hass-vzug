import httpx

from .appliance import ApplianceNetwork


def test_digest_auth_accepts_a_comma_in_the_uri() -> None:
    network = ApplianceNetwork()
    appliance = network.add("adora_dish_v6000", username="admin", password="secret")
    with httpx.Client(
        base_url=appliance.base_url,
        auth=httpx.DigestAuth("admin", "secret"),
        transport=network.transport(),
    ) as client:
        response = client.get("/hh?command=setX&value=a,b")

    assert response.status_code != 401
