import httpx
import pytest
import custom_components.vzug.api as api
import tests.fixtures.adora_slq.expected as expected_result
import tests.integration.test_core as test_core

BASE_URL = "http://127.0.0.1:5001"

########################################################################

vzug_client = api.VZugApi(BASE_URL)


@pytest.mark.asyncio
async def test_ai_get_device_status():
    await test_core.assert_ai_get_device_status_core(vzug_client, expected_result)


@pytest.mark.asyncio
async def test_ai_get_fw_version():
    await test_core.assert_ai_get_fw_version(vzug_client, expected_result)


@pytest.mark.asyncio
async def test_ai_get_last_push_notifications():
    await test_core.assert_ai_get_last_push_notifications(vzug_client, expected_result)


@pytest.mark.asyncio
async def test_ai_get_model_description():
    await test_core.assert_ai_get_model_description(vzug_client, expected_result)


@pytest.mark.asyncio
async def test_ai_get_mac_address():
    await test_core.assert_ai_get_mac_address(vzug_client)


@pytest.mark.asyncio
async def test_ai_get_update_status():
    await test_core.assert_ai_get_update_status(vzug_client, expected_result)


@pytest.mark.asyncio
async def test_hh_get_all_program_ids():
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await test_core.assert_hh_get_all_program_ids(vzug_client, expected_result)
    assert exc_info.value.response.status_code == 404


@pytest.mark.asyncio
async def test_hh_get_categories_and_commands():
    await test_core.assert_hh_get_categories_and_commands(vzug_client, expected_result)


@pytest.mark.asyncio
async def test_hh_get_device_info():
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await test_core.assert_hh_get_device_info(vzug_client, expected_result)
    assert exc_info.value.response.status_code == 404


@pytest.mark.asyncio
async def test_hh_get_eco_info():
    await test_core.assert_hh_get_eco_info(
        vzug_client, expected_result, expect_water=True, expect_energy=True
    )


@pytest.mark.asyncio
async def test_hh_get_fw_version():
    await test_core.assert_hh_get_fw_version(vzug_client, expected_result)


@pytest.mark.asyncio
async def test_hh_get_zh_mode():
    await test_core.assert_hh_get_zh_mode(vzug_client, expected_result)
