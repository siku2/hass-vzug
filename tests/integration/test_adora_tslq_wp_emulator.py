
import pytest

import custom_components.vzug.api as api
import tests.expected.adora_tslq_wp as expected_result
import tests.integration.test_core as test_core

BASE_URL = "http://127.0.0.1"

########################################################################
# Doing a fixture to create vzug_client not yet work.
# Async & Fixture seems a bad combo
#
# Because of the imports, this is the file to be copied per device
# Having multiple files also helps for the visualization of test result
########################################################################

@pytest.mark.asyncio
async def test_ai_get_device_status():
    vzug_client = api.VZugApi(BASE_URL)
    await test_core.assert_ai_get_device_status_core(vzug_client, expected_result)

@pytest.mark.asyncio
async def test_ai_get_fw_version():
    vzug_client = api.VZugApi(BASE_URL)
    await test_core.assert_ai_get_fw_version(vzug_client, expected_result)

@pytest.mark.asyncio
async def test_ai_get_last_push_notifications():
    vzug_client = api.VZugApi(BASE_URL)
    await test_core.assert_ai_get_last_push_notifications(vzug_client, expected_result)

@pytest.mark.asyncio
async def test_ai_get_model_description():
    vzug_client = api.VZugApi(BASE_URL)
    await test_core.assert_ai_get_model_description(vzug_client, expected_result)

@pytest.mark.asyncio
async def test_ai_get_mac_address():
    vzug_client = api.VZugApi(BASE_URL)
    await test_core.assert_ai_get_mac_address(vzug_client)

@pytest.mark.asyncio
async def test_ai_get_update_status():
    vzug_client = api.VZugApi(BASE_URL)
    await test_core.assert_ai_get_update_status(vzug_client, expected_result)

@pytest.mark.asyncio
async def test_hh_get_categories_and_hh_get_category():
    vzug_client = api.VZugApi(BASE_URL)
    await test_core.assert_hh_get_categories_and_hh_get_category(vzug_client, expected_result)

@pytest.mark.asyncio
async def test_hh_get_eco_info():
    vzug_client = api.VZugApi(BASE_URL)
    await test_core.assert_hh_get_eco_info(vzug_client, expected_result)

@pytest.mark.asyncio
async def test_hh_get_fw_version():
    vzug_client = api.VZugApi(BASE_URL)
    await test_core.assert_hh_get_fw_version(vzug_client, expected_result)

@pytest.mark.asyncio
async def test_hh_get_zh_mode():
    vzug_client = api.VZugApi(BASE_URL)
    await test_core.assert_hh_get_zh_mode(vzug_client, expected_result)

