from . import api


def get_device_name(device: api.DeviceStatus, model_name: str | None) -> str:
    name = device.get("DeviceName", "")
    if not name:
        name = model_name or ""
    if not name:
        name = device.get("Serial", "")
    return name
