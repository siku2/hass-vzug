import custom_components.vzug.api as api
from tests.fixtures.shared import category_expectation

### This file contains expected decoded results

ai_model_description = "AdoraDish V6000"

ai_device_status = api.DeviceStatus(
    DeviceName="Adora SL",
    Serial="46126 182263",
    Inactive="true",
    Program="",
    Status="Bitte Glanzmittel nachfüllen",
    ProgramEnd=api.DeviceStatusProgramEnd(EndType="0", End=""),
    deviceUuid="7738150909",
)

ai_firmware_version = api.AiFwVersion(
    fn="46126 182263",
    SW="1052633-R20",
    SD="1052633-R20",
    HW="1049255-R01",
    apiVersion="1.8.0",
    phy="WLAN",
    deviceUuid="7738150909",
)

ai_update_status = api.UpdateStatus(
    status="idle",
    isAIUpdateAvailable=False,
    isHHGUpdateAvailable=False,
    isSynced=True,
    components=[
        api.UpdateComponent(
            name="AI",
            running=False,
            available=False,
            required=False,
            progress=api.UpdateProgress(download=0, installation=0),
        ),
        api.UpdateComponent(
            name="HHG",
            running=False,
            available=False,
            required=False,
            progress=api.UpdateProgress(download=0, installation=0),
        ),
    ],
)

ai_last_push_notifications: list[api.PushNotification] = [
    api.PushNotification(
        date="2025-06-08T16:43:36Z",
        message="Glanzmittel nachfüllen!",
    ),
    api.PushNotification(
        date="2025-06-08T16:43:17Z",
        message="Programm Automatik beendet – Energie: 0,8 kWh, Wasser: 14 l",
    ),
]

hh_categories = [
    category_expectation("CATEGORY_0", 1, 7),
    category_expectation("CATEGORY_1", 1, 9),
    category_expectation("CATEGORY_2", 1, 17),
]

hh_total_commands = 182

hh_eco_info = api.EcoInfo(
    water=api.EcoInfoMetric(total=10783, average=17, program=14),
    energy=api.EcoInfoMetric(total=533, average=1.1, program=0.8)
)

hh_firmware_version = api.HhFwVersion(
    fn="46126 182263",
    an="7738150909",
    v="1056701-R28",
    vh1="1049255-R01",
    v2="1056700-R13",
    vh2="1084164-R01",
    vp="1090227-R17",
    vr0C="1090228-R19",
    vr01="1069783-R01",
)
