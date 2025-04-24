import logging
import os
import coloredlogs

DEVICE_CONF_FILE = "config.json"
RESPONSES_SUBDIR = "responses"

# Create a logger object.
logger = logging.getLogger(__name__)

# If you don't want to see log messages from libraries, you can pass a
# specific logger object to the install() function. In this case only log
# messages originating from that logger will show up on the terminal.
coloredlogs.install(level='DEBUG', logger=logger)

coloredlogs.install(fmt='%(asctime)s %(levelname)s %(message)s')

def fixtures_directory() -> str:
    return os.path.join(os.getenv("PROJECT_ROOT"), "tests/fixtures")

def device_directory(device_id) -> str:
    return os.path.join(os.getenv("PROJECT_ROOT"), "tests/fixtures", device_id)

def device_config_file(device_id) -> str:
    return os.path.join(os.getenv("PROJECT_ROOT"), "tests/fixtures", device_id, DEVICE_CONF_FILE)

def responses_directory(device_id) -> str:
    return os.path.join(os.getenv("PROJECT_ROOT"), "tests/fixtures", device_id, RESPONSES_SUBDIR)

def is_valid_device(device_id) -> bool:
    return os.path.exists(device_config_file(device_id))

def get_devices() -> str:
    """ Return list of subdirectories in fixtures"""
    fixtures_root = fixtures_directory()
    return [d for d in os.listdir(fixtures_root) if os.path.isdir(os.path.join(fixtures_root, d)) and d != '__pycache__']

class category_expectation:
    def __init__(self, id: str, count_description: int, count_commands):
        self.id = id
        self.count_description = count_description
        self.count_commands = count_commands
