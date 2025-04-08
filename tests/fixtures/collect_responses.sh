#!/bin/bash

###############################################################################
# Collect responses from the API and save them to files
###############################################################################

# Check if the correct number of arguments is provided
if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <DEVICE_ID> <IP_ADDRESS>"
    exit 1
fi

# Assign command line arguments to variables
BASE_URL="http://$2"
DEVICE_ID=$1

# Validate BASE_URL to ensure it is a proper absolute URL
if ! [[ $BASE_URL =~ ^http://[a-zA-Z0-9.-]+(:[0-9]+)?$ ]]; then
    echo "Error: Invalid IP address or URL format for BASE_URL: $BASE_URL"
    exit 1
fi

# Validate DEVICE_ID to be alphanumeric without spaces
if ! [[ $DEVICE_ID =~ ^[a-zA-Z0-9_-]+$ ]]; then
    echo "Error: Invalid DEVICE_ID format. '$DEVICE_ID' should be alphanumeric and can have _ or -."
    exit 1
fi

# Check if supdirectory $DEVICE_ID exists. Abort if it exists
if [ -d "$DEVICE_ID" ]; then
#ask to delete the directory with all its contents
    echo "Directory $DEVICE_ID already exists. Do you want to delete it? (y/n)"
    read -r answer
    if [[ $answer == "y" ]]; then
        rm -rf "$DEVICE_ID"
        echo "Directory $DEVICE_ID deleted."
    else
        echo "Exiting without deleting the directory."
        exit 1
    fi
fi

#create the directory for the device ID
mkdir -p "$DEVICE_ID"

echo "Collecting responses for $DEVICE_ID from $BASE_URL ..."

# Define the APIs to collect
declare -A responses
responses=(
    ["ai_get_devicestatus.json"]="{$BASE_URL}/ai?command=getDeviceStatus"
    ["ai_get_fwversion.json"]="{$BASE_URL}/ai?command=getFWVersion"
    ["ai_get_lastpushnotifications.json"]="{$BASE_URL}/ai?command=getLastPUSHNotifications"
    ["ai_get_macaddress.txt"]="{$BASE_URL}/ai?command=getMacAddress"
    ["ai_get_modeldescription.txt"]="{$BASE_URL}/ai?command=getModelDescription"
    ["ai_get_updatestatus.json"]="{$BASE_URL}/ai?command=getUpdateStatus"

    ["hh_get_categories.json"]="{$BASE_URL}/hh?command=getCategories"
    ["hh_get_category_userxsettings.json"]="{$BASE_URL}/hh?command=getCategory&value=UserXsettings"
    ["hh_get_category_ecomanagement.json"]="{$BASE_URL}/hh?command=getCategory&value=EcoManagement"
    ["hh_get_commands.json"]="{$BASE_URL}/hh?command=getCommands"
    ["hh_get_ecoinfo.json"]="{$BASE_URL}/hh?command=getEcoInfo"
    ["hh_get_fwversion.json"]="{$BASE_URL}/hh?command=getFWVersion"
    ["hh_get_zhmode.json"]="{$BASE_URL}/hh?command=getZHMode"   
)

#loop through the APIs and collect responses and save them to files
for filename in "${!responses[@]}"; do
    url=${responses[$filename]}
    # Use curl to fetch the response and save it to a file

    filename_tmp="./$DEVICE_ID/response.tmp"

    # Use curl to fetch rest api GET request
    curl -s -o "$filename_tmp" "$url"

    # Check if the curl command was successful
    if [ $? -ne 0 ]; then
        echo "Error: Failed to fetch data from $url"
        exit 1
    elif  [ ! -s "$filename_tmp" ]; then
        # Check if the file is empty
        echo "Error: The response from $url is empty."
        rm "$filename_tmp"
        exit
    fi

    # if file extension is .txt
    if [[ $filename == *.txt ]]; then
        # Rename the temporary file to .txt
        mv "$filename_tmp" "./$DEVICE_ID/$filename"
        echo "Response saved to ./$DEVICE_ID/$filename"
    elif [[ $filename == *.json ]]; then
        # Format the json file
        jq '.' "$filename_tmp" > "./$DEVICE_ID/$filename" && rm "$filename_tmp"
        echo "Response saved to ./$DEVICE_ID/$filename"
    else
        # If the file extension is not recognized, delete the temporary file
        echo "Error: Unrecognized file type for ./$DEVICE_ID/$filename. Deleting temporary file."
        rm "$filename_tmp"
    fi 
    
done

# Create random serial numbers of format "nnnnn mmmmmm"
SERIAL_NUMBER_1="$(shuf -i 10000-99999 -n 1) $(shuf -i 100000-999999 -n 1)"
SERIAL_NUMBER_2="$(shuf -i 1000000000-9999999999 -n 1)"

# Create random device UUID of format "nnnnnnnnnn"
DEVICE_UID="$(shuf -i 1000000000-9999999999 -n 1)"
# Create random MAC address of format "02:nn:nn:nn:nn:nn"
MAC_ADDRESS="$(printf '02:%02X:%02X:%02X:%02X:%02X' $(shuf -i 0-255 -n 5))"
echo "Random serial numbers and device uuid"

# Randomaize serial numbers in different files
sed -i -E "s/\"Serial\": \"[0-9 ]+\"/\"Serial\": \"$SERIAL_NUMBER_1\"/g"   "./$DEVICE_ID/ai_get_devicestatus.json"

sed -i -E "s/\"fn\": \"[0-9 ]+\"/\"fn\": \"$SERIAL_NUMBER_1\"/g"           "./$DEVICE_ID/ai_get_fwversion.json"
sed -i -E "s/\"fn\": \"[0-9 ]+\"/\"fn\": \"$SERIAL_NUMBER_1\"/g"           "./$DEVICE_ID/hh_get_fwversion.json"

sed -i -E "s/\"an\": \"[0-9]+\"/\"an\": \"$SERIAL_NUMBER_2\"/g"            "./$DEVICE_ID/ai_get_fwversion.json"
sed -i -E "s/\"an\": \"[0-9]+\"/\"an\": \"$SERIAL_NUMBER_2\"/g"            "./$DEVICE_ID/hh_get_fwversion.json"

# Randomize deviceUuid in different files
sed -i -E "s/\"deviceUuid\": \"[0-9]+\"/\"deviceUuid\": \"$DEVICE_UID\"/g" "./$DEVICE_ID/ai_get_devicestatus.json"
sed -i -E "s/\"deviceUuid\": \"[0-9]+\"/\"deviceUuid\": \"$DEVICE_UID\"/g" "./$DEVICE_ID/ai_get_fwversion.json"
sed -i -E "s/\"deviceUuid\": \"[0-9]+\"/\"deviceUuid\": \"$DEVICE_UID\"/g" "./$DEVICE_ID/hh_get_fwversion.json"

# replace the MAC address in the file
sed -i -E "s/[0-9a-fA-F:]+/$MAC_ADDRESS/g" "$DEVICE_ID/ai_get_macaddress.txt"
