from flask import Flask, jsonify, request, send_from_directory
import argparse
import os

app = Flask(__name__)

def register_routes(app, response_directory):

    if not os.path.exists(response_directory):
        print(f"Error: Directory {response_directory} does not exist.")
        exit(1)

    else:
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

    debug = True
    if debug:
        register_routes(app, f"/workspaces/homeassistant-vzug/tests/fixtures/adora_tslq_test")
        app.run(debug=True)
    else:        
        # Parse command line arguments
        parser = argparse.ArgumentParser(description="Start the emulator with a specific device ID.")
        parser.add_argument("--device-id", required=True, help="The device ID to use for the emulator.")
        args = parser.parse_args()

        # Print the device ID to confirm it's being used
        print(f"Emulator started with device ID: {args.device_id}")

        register_routes(app, args.device_id)
        app.run(debug=True)
