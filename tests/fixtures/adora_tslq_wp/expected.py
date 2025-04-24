
import custom_components.vzug.api as api
from tests.fixtures.shared import category_expectation

### This file contains expected decoded results

ai_model_description = "Adora TSLQ WP"

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
        date = "2025-02-16T10:09:32Z",
        message = "Knitterschutz endet in 5 Minuten - bitte entnehmen Sie die Wäsche!"
    ),
    api.PushNotification(
        date = "2025-02-16T09:43:33Z",
        message = "Programm Korb beendet. - Energie:  0,4 kWh."
    )
]

hh_categories = [
    category_expectation("UserXsettings", 1, 8),
    category_expectation("EcoManagement", 1, 5)
]

hh_total_commands = 56

hh_eco_info = api.EcoInfo(

    energy = api.EcoInfoMetric(
        total = 4.424,
        average = 0.737,
        program = 0.411
    )
)

hh_firmware_version = api.HhFwVersion(
    fn = "98765 012345",
    an = "9876500000",
    v = "W5640910",
    v2 = "W564197",
    vp = "W563844",
    vh1 = "W5640008",
    vh2 = "W56420R03",
    vr01 = "W564083"
)

hh_firmware_version["main-ressource"] = "W5642905"
hh_firmware_version["device-type"] = "KUNDE"
