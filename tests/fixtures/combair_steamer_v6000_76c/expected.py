### Expected decoded results for CombairSteamer V6000 76C."""

import custom_components.vzug.api as api

ai_model_description = "CombairSteamer V6000 76C"

ai_device_status = api.DeviceStatus(
    DeviceName="",
    Serial="40695 200742",
    Inactive="true",
    Program="",
    Status="",
    ProgramEnd=api.DeviceStatusProgramEnd(EndType="0", End=""),
    deviceUuid="7593387505",
)

ai_firmware_version = api.AiFwVersion(
    fn="40695 200742",
    SW="1052633-R20",
    SD="1052633-R20",
    HW="1022913-R08",
    apiVersion="1.8.0",
    phy="WLAN",
    deviceUuid="7593387505",
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
        date="2025-06-08T01:03:03Z",
        message="Bitte schliessen Sie die Tür.",
    ),
    api.PushNotification(date="2025-06-08T01:01:26Z", message="Aufgeheizt"),
]

hh_categories = []

hh_total_commands = 0

hh_eco_info = api.EcoInfo(
    energy=api.EcoInfoMetric(total=277.709, average=0.561, program=0.438)
)

hh_firmware_version = api.HhFwVersion(
    an="7593387505",
    fn="40695 200742",
    m="CSB",
    v="1044431-R34",
    softwareModelId=336,
    syv="1088181-R44",
    vp="1053702-R34",
    vr00="1051665-R45",
    vr01="1090215-R15",
    vr0A="1053702-R34",
    vr0C="1098361-R27",
    vr0D="1098362-R07",
    vr0E="1098360-R06",
    vr0F="1098359-R11",
    vr10="1033360-R04",
    vr13="1098358-R29",
    v2="1033359-R27",
    vh1="1022913-R08",
    vh2="1067747-R04",
    v3="1031584-R05",
    vh3="1086324-R05",
    vr21="06000015FFF",
    ZHSW="1052633-R20",
)

hh_zh_mode = 2
