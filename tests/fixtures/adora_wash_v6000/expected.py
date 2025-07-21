### Expected decoded results for AdoraWash V6000."""

import custom_components.vzug.api as api
from tests.fixtures.shared import category_expectation

ai_model_description = "AdoraWash V6000"

ai_device_status = api.DeviceStatus(
    DeviceName="",
    Serial="33147 536171",
    Inactive="true",
    Program="",
    Status="",
    ProgramEnd=api.DeviceStatusProgramEnd(EndType="0", End=""),
    deviceUuid="7531027869",
)

ai_firmware_version = api.AiFwVersion(
    fn="33147 536171",
    SW="1052633-R20",
    SD="1052633-R20",
    HW="1077219-R05",
    apiVersion="1.8.0",
    phy="WLAN",
    deviceUuid="7531027869",
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
        date="2025-06-05T12:47:17Z",
        message="Programm 20°C WetClean beendet – Energie: 0,1kWh, Wasser: 38ℓ",
    ),
    api.PushNotification(
        date="2025-06-05T07:55:21Z",
        message="Programm 40°C Daunen beendet – Energie: 0,5kWh, Wasser: 99ℓ",
    ),
]

hh_categories = [
    category_expectation("settings", 1, 15),
    category_expectation("ecoManagement", 1, 5),
]

hh_total_commands = 87

hh_device_info = api.DeviceInfo(
    model="AS6TDI",
    description="AdoraDish V6000",
    type="GS",
    name="Adora SL",
    serialNumber="33147 536171",
    articleNumber="7531027869",
    apiVersion="1.8.0",
    zhMode=2,
)

hh_eco_info = api.EcoInfo(
    water=api.EcoInfoMetric(total=0, average=0, program=0),
    energy=api.EcoInfoMetric(total=0, average=0, program=0),
)

hh_firmware_version = api.HhFwVersion(
    fn="33147 536171",
    an="7531027869",
    v="1032589-R18",
    vr01="1032596-R03",
    v2="1032591-R06",
    vr10="1032592-R02",
    vi2="1039144-R01",
    vh1="1077219-R05",
    vh2="1037281-R07",
    vr0B="1069346-R05",
    vp="1064277-R21",
    vr0C="1069072-R01",
    vr0E="1032590-R03",
    Mh="???????-???",
    MD="???????-???",
    Zh="???????-???",
    ZV="???????-???",
    ZHSW="1052633-R20",
)

hh_all_program_ids = list[int](
    [
        3021,
        3016,
        3015,
        3020,
        3017,
        3018,
        3019,
        3000,
        3008,
        3009,
        3002,
        3007,
        3003,
        3011,
        3004,
        3006,
        3005,
        3014,
        3012,
        3001,
        3010,
        3013,
    ]
)

hh_zh_mode = 2
