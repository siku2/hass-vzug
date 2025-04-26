
import custom_components.vzug.api as api
from tests.fixtures.shared import category_expectation

### This file contains expected decoded results

ai_model_description = "Adora SLQ"

ai_device_status = api.DeviceStatus(
    DeviceName="",
    Serial="98765 012345",
    Inactive="true",
    Program="",
    Status="",
    ProgramEnd=api.DeviceStatusProgramEnd(EndType="0", End=""),
    deviceUuid="1122334455"
)

ai_firmware_version = api.AiFwVersion(
    fn = "98765 012345",
    SW = "1052633-R20",
    SD = "1052633-R20",
    HW = "1065944-R02",
    apiVersion = "1.8.0",
    phy = "WLAN",
    deviceUuid = "1122334455"
)

ai_update_status = api.UpdateStatus(

    status = "idle",
    isAIUpdateAvailable = False,
    isHHGUpdateAvailable = False,
    isSynced = True,
    components =
    [
        api.UpdateComponent(
            name = "AI",
            running = False,
            available = False,
            required = False,
            progress = api.UpdateProgress(
                download = 0,
                installation = 0
            )
        ),
        api.UpdateComponent(
            name = "HHG",
            running = False,
            available = False,
            required = False,
            progress = api.UpdateProgress(
                download = 0,
                installation = 0
            )
        )
    ]
)

ai_last_push_notifications: list[api.PushNotification] = [
    api.PushNotification(
        date = "2025-04-13T17:15:13Z",
        message = "Programm 30°C Ecoprogramm beendet - Energie: 0,4kWh, Wasser: 45ℓ."
    ),
    api.PushNotification(
        date = "2025-04-13T15:14:50Z",
        message = "Programm 40°C Dampfglätten beendet - Energie: 0,3kWh, Wasser: 1ℓ."
    )
]

hh_categories = [
    category_expectation("settings", 1, 19)
]

hh_total_commands = 82

hh_eco_info = api.EcoInfo(

    energy = api.EcoInfoMetric(
        total = 96.3,
        average = 0.5,
        program = 0.4
    )
)

hh_firmware_version = api.HhFwVersion(
    fn = "98765 012345",
    an = "9876500000",
    v = "W4215911",
    v2 = "W421095",
    vp = "W422046",
    vh1 = "W4215009",
    vh2 = "W4211304",
    v3 = "W424921"
)
