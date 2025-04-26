import re


async def assert_ai_get_device_status_core(vzug_client, expected_result):
    device_status = await vzug_client.get_device_status()

    assert device_status["DeviceName"] == expected_result.ai_device_status["DeviceName"]
    assert is_valid_serial_type_1(device_status["Serial"])
    assert device_status["Inactive"] == expected_result.ai_device_status["Inactive"]
    assert device_status["Program"] == expected_result.ai_device_status["Program"]
    assert device_status["Status"] == expected_result.ai_device_status["Status"]
    assert device_status["ProgramEnd"]["End"] == expected_result.ai_device_status["ProgramEnd"]["End"]
    assert device_status["ProgramEnd"]["EndType"] == expected_result.ai_device_status["ProgramEnd"]["EndType"]
    assert is_valid_serial_type_2(device_status["deviceUuid"])

async def assert_ai_get_fw_version(vzug_client, expected_result):
    fw_version = await vzug_client.get_ai_fw_version()

    assert is_valid_serial_type_1(fw_version["fn"])
    assert fw_version["SW"] == expected_result.ai_firmware_version["SW"]
    assert fw_version["SD"] == expected_result.ai_firmware_version["SD"]
    assert fw_version["HW"] == expected_result.ai_firmware_version["HW"]
    assert fw_version["apiVersion"] == expected_result.ai_firmware_version["apiVersion"]
    assert fw_version["phy"] == expected_result.ai_firmware_version["phy"]
    assert is_valid_serial_type_2(fw_version["deviceUuid"])

async def assert_ai_get_last_push_notifications(vzug_client, expected_result):
    last_push_notifications = await vzug_client.get_last_push_notifications()

    for i in range(len(expected_result.ai_last_push_notifications)):
        assert last_push_notifications[i]["date"] == expected_result.ai_last_push_notifications[i]["date"]
        assert last_push_notifications[i]["message"] == expected_result.ai_last_push_notifications[i]["message"]

async def assert_ai_get_model_description(vzug_client, expected_result):
    model_description = await vzug_client.get_model_description()
    assert model_description.replace(" Emulator", "") == expected_result.ai_model_description

async def assert_ai_get_mac_address(vzug_client):
    mac_info = await vzug_client.get_mac_address()
    assert is_valid_macaddr802(mac_info)

async def assert_ai_get_update_status(vzug_client, expected_result):
    update_status = await vzug_client.get_update_status()

    assert update_status["status"] == expected_result.ai_update_status["status"]
    assert update_status["isAIUpdateAvailable"] == expected_result.ai_update_status["isAIUpdateAvailable"]
    assert update_status["isHHGUpdateAvailable"] == expected_result.ai_update_status["isHHGUpdateAvailable"]
    assert update_status["isSynced"] == expected_result.ai_update_status["isSynced"]

    for i in range(len(expected_result.ai_update_status["components"])):
        assert update_status["components"][i]["name"] == expected_result.ai_update_status["components"][i]["name"]
        assert update_status["components"][i]["running"] == expected_result.ai_update_status["components"][i]["running"]
        assert update_status["components"][i]["available"] == expected_result.ai_update_status["components"][i]["available"]
        assert update_status["components"][i]["required"] == expected_result.ai_update_status["components"][i]["required"]
        assert update_status["components"][i]["progress"]["download"] == expected_result.ai_update_status["components"][i]["progress"]["download"]
        assert update_status["components"][i]["progress"]["installation"] == expected_result.ai_update_status["components"][i]["progress"]["installation"]

async def assert_hh_get_categories_and_commands(vzug_client, expected_result):
    categories = await vzug_client.list_categories()

    assert len(categories) == len(expected_result.hh_categories)
    total_commands = 0

    for i in range(len(expected_result.hh_categories)):
        assert categories[i] == expected_result.hh_categories[i].id

        category = await vzug_client.get_category(categories[i])
        assert len(category) == expected_result.hh_categories[i].count_description

        commands = await vzug_client.list_commands(categories[i])
        assert len(commands) == expected_result.hh_categories[i].count_commands

        for curr_command in commands:
            details = await vzug_client.get_command(curr_command)
            total_commands = total_commands + len(details)

    # Rather artifical number. But still a good inidcator whether we got all the details
    assert total_commands == expected_result.hh_total_commands

async def assert_hh_get_eco_info(vzug_client, expected_result):
    eco_info = await vzug_client.get_eco_info()

    assert eco_info["energy"]["total"]   == expected_result.hh_eco_info["energy"]["total"]
    assert eco_info["energy"]["average"] == expected_result.hh_eco_info["energy"]["average"]
    assert eco_info["energy"]["program"] == expected_result.hh_eco_info["energy"]["program"]

async def assert_hh_get_fw_version(vzug_client, expected_result):
    fw_version = await vzug_client.get_hh_fw_version()

    for key, value in expected_result.hh_firmware_version.items():
        if key == "fn" or key == "Serial":
            assert is_valid_serial_type_1(fw_version[key])
        elif  key == "an" or key == "deviceUuid":
            assert is_valid_serial_type_2(fw_version[key])
        else:
            # For other keys, just compare the values directly
            assert fw_version[key].strip() == value.strip()

async def assert_hh_get_zh_mode(vzug_client, expected_result):
    #zh_mode = await vzug_client.get_zh_mode()
    assert 1 == 0


def is_valid_macaddr802(value):
    return  re.search("^([0-9A-F]{2}[-]){5}([0-9A-F]{2})$|^([0-9A-F]{2}[:]){5}([0-9A-F]{2})$", value, re.IGNORECASE) is not None

def is_valid_serial_type_1(value):
    ### Check if serial number is of the form 12345 123456
    return re.search("^[0-9]{5} [0-9]{6}$", value) is not None

def is_valid_serial_type_2(value):
    ### Check for 10 digit serial number or deviceUUID
    return re.search("^[0-9]{10}$", value) is not None

