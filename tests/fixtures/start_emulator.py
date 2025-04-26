import os

from flask import Flask, jsonify, request, send_from_directory

app = Flask("V-Zug Emulator")

def register_routes(app, response_directory):

    @app.route("/ai", methods=["GET"])
    def handle_ai_request():
        # extract params from request
        command = request.args.get('command')
        if command == "getDeviceStatus":
            return send_from_directory(response_directory, "ai_get_devicestatus.json")
        elif command == "getFWVersion":
            return send_from_directory(response_directory, "ai_get_fwversion.json")
        elif command == "getLastPUSHNotifications":
            return send_from_directory(response_directory, "ai_get_lastpushnotifications.json")
        elif command == "getMacAddress":
            return send_from_directory(response_directory, "ai_get_macaddress.txt")
        elif command == "getModelDescription":
            return send_from_directory(response_directory, "ai_get_modeldescription.txt")
        elif command == "getUpdateStatus":
            return send_from_directory(response_directory, "ai_get_updatestatus.json")
        else:
            return jsonify({"error": "Unsupported command"}), 400

    @app.route("/hh", methods=["GET"])
    def handle_hh_request():
        # extract params from request
        command = request.args.get('command')
        value = request.args.get('value')

        if command == "getCategories":
            return send_from_directory(response_directory, "hh_get_categories.json")
        elif command == "getCategory":
            if value == "UserXsettings":
                return send_from_directory(response_directory, "hh_get_category_userxsettings.json")
            elif value == "EcoManagement":
                return send_from_directory(response_directory, "hh_get_category_ecomanagement.json")
            else:
                return jsonify({"error": "Unsupported value"}), 400
        elif command == "getCommands":
            return send_from_directory(response_directory, "hh_get_commands.json")
        elif command == "getEcoInfo":
            return send_from_directory(response_directory, "hh_get_ecoinfo.json")
        elif command == "getFWVersion":
            return send_from_directory(response_directory, "hh_get_fwversion.json")
        elif command == "getZHMode":
            return send_from_directory(response_directory, "hh_get_zhmode.json")
        else:
            return jsonify({"error": "Unsupported command"}), 400


if __name__ == "__main__":

    response_root = f"{os.getenv("PROJECT_ROOT")}/tests/fixtures"
    # Show list of subdirectories in the current directory
    subdirectories = [d for d in os.listdir(response_root) if os.path.isdir(os.path.join(response_root, d))]

    # Select the device to be used
    print("Devices:")
    for idx, subdir in enumerate(subdirectories, start=1):
        print(f"{idx}: {subdir}")

    response_id = input("Please enter device # use: ")
    if not response_id.isdigit() or int(response_id) < 1 or int(response_id) > len(subdirectories):
        print("Invalid device ID. Please enter a valid number.")
        exit(1)

    response_directory = os.path.join(response_root, subdirectories[int(response_id)-1])

    register_routes(app, response_directory)
    app.run(port=80)

