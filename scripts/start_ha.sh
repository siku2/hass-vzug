#!/usr/bin/env bash

set -e

# When started as task in VSCode, add necessary path
export PATH="$HOME/.local/bin:$PATH"

cd "$(dirname "$0")/.."

# Skip if Home Assistant (hass) is present
if pgrep -x "hass" > /dev/null; then
    echo "----------------------------------------------------------------------"
    echo "Home Assistant is already running ..."
    echo "----------------------------------------------------------------------"
    exit 0
fi

# Create config dir if not present
if [[ ! -d "${PWD}/config" ]]; then
    mkdir -p "${PWD}/config"
    hass --config "${PWD}/config" --script ensure_config
fi

# Set the path to custom_components
## This let's us have the structure we want <root>/custom_components/integration_blueprint
## while at the same time have Home Assistant configuration inside <root>/config
## without resulting to symlinks.
export PYTHONPATH="${PYTHONPATH}:${PWD}/custom_components"

# Start Home Assistant

echo "----------------------------------------------------------------------"
echo "Start Home Assistant ..."
echo "----------------------------------------------------------------------"

hass --config "${PWD}/config" --debug
