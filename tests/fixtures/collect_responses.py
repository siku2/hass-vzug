import argparse
import json
import logging
import os
import random
import requests

from pathlib import Path
from tests.fixtures import shared
from time import sleep

class record_call:
    def __init__(self, resulting_filename: str, relative_url: str, category_special: bool, de_identify_mac: bool):
        self.resulting_filename = resulting_filename
        self.relative_url = relative_url
        self.category_special = category_special
        self.de_identify_mac = de_identify_mac

class category_details:
    def __init__(self, id: str, category: dict, commands):
        self.id = id
        self.category = category
        self.commands = commands

class command_details:
    def __init__(self, id: str, details: dict):
        self.id = id
        self.details = details

def collect_responses(device_id):
    """
    Collect all JSON responses from predefined URLs and create different results
    """

    config = get_config_from_existing_file(device_id)

    response_root = shared.responses_directory(device_id)

    # with the result from getCategories one should loop through getCategory & getCommands

    record_calls = {

        record_call("ai_get_devicestatus.json", "/ai?command=getDeviceStatus", False, False),
        record_call("ai_get_fwversion.json", "/ai?command=getFWVersion", False, False),
        record_call("ai_get_lastpushnotifications.json", "/ai?command=getLastPUSHNotifications", False, False),
        record_call("ai_get_macaddress.txt", "/ai?command=getMacAddress", category_special=False, de_identify_mac=True),
        record_call("ai_get_modeldescription.txt", "/ai?command=getModelDescription", False, False),
        record_call("ai_get_updatestatus.json", "/ai?command=getUpdateStatus", False, False),

        record_call("NA", "/hh?command=getCategories", category_special=True, de_identify_mac=False),

        record_call("hh_get_ecoinfo.json", "/hh?command=getEcoInfo", False, False),
        record_call("hh_get_fwversion.json", "/hh?command=getFWVersion", False, False),
        record_call("hh_get_zhmode.json", "/hh?command=getZHMode", False, False),

        record_call("ai_get_invalid_command.txt", "/ai?command=getErrorAnswer42", False, False),
        record_call("hh_get_invalid_command.txt", "/hh?command=getErrorAnswer42", False, False),
    }

    for current_call in record_calls:
        url = config["base_url"] + current_call.relative_url

        output_file = os.path.join(response_root, current_call.resulting_filename)

        i = 0
        while (i < 10):
            response = requests.get(url.strip())
            if response.status_code == 503:
                logging.warning(f" {current_call.relative_url}: {response.status_code} - {response.text}")
                sleep(2)
                i += 1
            else:
                break

        if current_call.category_special:
            collect_categories_details( \
                os.path.join(response_root,"hh_get_categories.json"), \
                os.path.join(response_root,"hh_get_command_details.json"), \
                config["base_url"], response.json())

        elif current_call.resulting_filename.endswith('.txt'):

            if current_call.resulting_filename == "ai_get_macaddress.txt":
                # More general purpose search was not worth it yet
                with open(output_file, 'w') as f:
                    f.write(config["fake_mac_address"])
            elif current_call.resulting_filename == "ai_get_modeldescription.txt":
                with open(output_file, 'w') as f:
                    f.write(f"{response.text} Emulator")
            else:
                with open(output_file, 'w') as f:
                    f.write(response.text)

            logging.info(f"Response saved to {output_file}")

        elif current_call.resulting_filename.endswith('.json'):

            response_json=response.json()
            if "Serial" in response_json:
                response_json["Serial"] = config["fake_device_serial_1"]
            if "fn" in response_json:
                response_json["fn"] = config["fake_device_serial_1"]
            if "an" in response_json:
                response_json["an"] = config["fake_device_serial_2"]
            if "deviceUuid" in response_json:
                response_json["deviceUuid"] = config["fake_device_serial_2"]

            if "400.03" in response.text:
                logging.error(f"The response from {url} contains 400.03 error.")
            else:
                with open(output_file, 'w') as f:
                    json.dump(response_json, f, indent=2, ensure_ascii=False)
                logging.info(f"Response saved to {output_file}")
        else:
            logging.error(f"Error: Unrecognized file type for {output_file}. Skipped collecting response.")


def collect_categories_details(filename_categories: str, filename_commands: str, base_url: str, categories_json: dict):

    categories = []

    all_command_details = []

    # Don't really know what the commands means for the different categories
    for curr_category_id in categories_json:
        category_url = f"{base_url}/hh?command=getCategory&value={curr_category_id}"
        command_url = f"{base_url}/hh?command=getCommands&value={curr_category_id}"

        category = requests.get(category_url).json()
        commands = requests.get(command_url).json()

        categories.append(category_details(curr_category_id, category, commands))

        # Get next level down json. Based on the API, the commands need to be device unique
        for curr_command in commands:
            command_url = f"{base_url}/hh?command=getCommand&value={curr_command}"
            command_details_json = requests.get(command_url).json()
            all_command_details.append(command_details(curr_command, command_details_json))


    categories_data = [{"id": c.id, "category": c.category, "commands": c.commands} for c in categories]
    details_data = [{"id": d.id, "details": d.details} for d in all_command_details]

    with open(filename_categories, 'w') as f:
        json.dump(categories_data, f, indent=2, ensure_ascii=False)

    with open(filename_commands, 'w') as f:
        json.dump(details_data, f, indent=2, ensure_ascii=False)

    logging.info(f"Response saved to {filename_categories}")
    logging.info(f"Response saved to {filename_commands}")


def rmdir(directory):
    directory = Path(directory)
    for item in directory.iterdir():
        if item.is_dir():
            rmdir(item)
        else:
            item.unlink()
    directory.rmdir()

def get_config_from_existing_file(device_id) -> dict:
    with open(shared.device_config_file(device_id)) as f:
        config = json.load(f)

    return config

def get_config_from_user_and_save(device_id):

    if not os.path.exists(shared.device_directory(device_id)):
        os.makedirs(shared.device_directory(device_id))

        ip_address = input("Please enter IP address: ")

        # Create random serial numbers of format "nnnnn mmmmmm"
        serial_number_1 = f"{random.randint(10000, 99999)} {random.randint(100000, 999999)}"
        serial_number_2 = f"{random.randint(1000000000, 9999999999)}"

        # Create random MAC address of format "02:nn:nn:nn:nn:nn"
        mac_address = "02:" + ":".join(f"{random.randint(0, 255):02x}" for _ in range(5))

        # store in config.json
        config = {
            "base_url": f"http://{ip_address}",
            "fake_mac_address": mac_address,
            "fake_device_serial_1": serial_number_1,
            "fake_device_serial_2": serial_number_2
        }
        with open(shared.device_config_file(device_id), 'w') as f:
            json.dump(config, f, indent=2)


def select_device() -> str:
    """ Used for interactive debugging, when no command line parameters are provided """

    devices = shared.get_devices()

    # Select the device to be used
    print("")
    print("--------------------------------------------------------------------------------------")
    print("Select an existing device or create a new one.")
    print("- When 0 is selected and the device already exists, it will be completely overwritten.")
    print("- When an existing device is selected only the responses will be deleted.")
    print("--------------------------------------------------------------------------------------")
    print("0: New device")

    for idx, device in enumerate(devices, start=1):
        print(f"{idx}: {device}")

    print("")

    response_id = input("Please enter device number: ")

    if int(response_id) == 0:
        device_id = input("Specify new device ID: ")
        if os.path.exists(shared.device_directory(device_id)):
            rmdir(shared.device_directory(device_id))
    else:
        device_id = devices[int(response_id) - 1]

    if not shared.is_valid_device(device_id):
        get_config_from_user_and_save(device_id)

    # Eventually, we want to have multiple responses for the same device
    responses_dir = shared.responses_directory(device_id)
    if os.path.exists(shared.responses_directory(device_id)):
        print(f"Responses for device {device_id} already exists. Delete exiting ones")
        rmdir(responses_dir)
        print("")

    os.makedirs(responses_dir)

    return device_id


def main():
    parser = argparse.ArgumentParser(description='Collect JSON responses from predefined URLs into a single file')
    parser.add_argument('--device_id',  required=False, help='Output JSON file path')

    args = parser.parse_args()

    if args.device_id and shared.is_valid_device(args.device_id):
        collect_responses(args.device_id)
    else:
        print ("No port or device_id provided or device config not found. Starting interactive mode.")
        device = select_device()
        collect_responses(device)

if __name__ == '__main__':
    main()
