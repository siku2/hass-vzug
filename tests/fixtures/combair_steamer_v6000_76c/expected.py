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

hh_device_info = api.DeviceInfo(
    model="CSB",
    description="CombairSteamer V6000 76C",
    type="ST",
    name="",
    serialNumber="40695 200742",
    articleNumber="7593387505",
    apiVersion="1.11.0",
    zhMode=2,
)


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

hh_all_program_ids = list[int](
    [
        4,
        5,
        6,
        7,
        8,
        9,
        10,
        11,
        12,
        14,
        15,
        21,
        27,
        28,
        29,
        30,
        31,
        32,
        33,
        34,
        35,
        42,
        44,
        48,
        49,
        101,
        106,
        107,
        109,
        113,
        114,
        116,
        117,
        118,
        119,
        120,
        122,
        123,
        124,
        125,
        126,
        127,
        128,
        129,
        130,
        131,
        132,
        133,
        136,
        141,
        142,
        143,
        146,
        150,
        158,
        169,
        170,
        171,
        174,
        175,
        177,
        179,
        180,
        181,
        182,
        184,
        186,
        187,
        189,
        190,
        192,
    ]
)

hh_zh_mode = 2

aggregate_meta = api.AggMeta(
    mac_address="02:56:61:f8:c4:21",
    model_id="CSB",
    model_name="CombairSteamer V6000 76C",
    device_name="",
    serial_number="40695 200742",
    api_version=(1, 11, 0),
)

