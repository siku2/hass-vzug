import logging
from pathlib import Path

import coloredlogs

DEVICE_CONF_FILE = "config.json"
RESPONSES_SUBDIR = "responses"

# Create a logger object.
logger = logging.getLogger(__name__)

# If you don't want to see log messages from libraries, you can pass a
# specific logger object to the install() function. In this case only log
# messages originating from that logger will show up on the terminal.
coloredlogs.install(level="DEBUG", logger=logger)

coloredlogs.install(fmt="%(asctime)s %(levelname)s %(message)s")


def fixtures_directory() -> Path:
    return Path(__file__).resolve().parent


def device_directory(device_id) -> Path:
    return fixtures_directory() / device_id


def device_config_file(device_id) -> Path:
    return device_directory(device_id) / DEVICE_CONF_FILE


def responses_directory(device_id) -> Path:
    return device_directory(device_id) / RESPONSES_SUBDIR


def is_valid_device(device_id) -> bool:
    return device_config_file(device_id).exists()


def get_devices() -> list[str]:
    """Return list of subdirectories in fixtures"""
    return sorted(
        d.name
        for d in fixtures_directory().iterdir()
        if d.is_dir() and d.name != "__pycache__"
    )


class category_expectation:
    def __init__(self, id: str, count_description: int, count_commands):
        self.id = id
        self.count_description = count_description
        self.count_commands = count_commands
