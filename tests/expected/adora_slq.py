
import custom_components.vzug.api as api

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
        date = "2025-04-10T18:15:27Z",
        message = "Programm 40°C Ecoprogramm beendet - Energie: 0,5kWh, Wasser: 42ℓ."
    ),
    api.PushNotification(
        date = "2025-04-05T20:58:43Z",
        message = "Programm 60°C Buntwäsche beendet - Energie: 0,9kWh, Wasser: 35ℓ."
    )
]

## Pretty silly getCatergory API just returns one value
hh_categories: list[(str, str)] = [
    ("UserXsettings", {'description': 'Benutzereinstellungen'}),
    ("EcoManagement", {'description': "EcoManagement"})
]


hh_eco_info = api.EcoInfo(

    energy = api.EcoInfoMetric(
        total = 90.4,
        average = 0.5,
        program = 0.5
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