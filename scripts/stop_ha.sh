#!/usr/bin/env bash

# Skip if Home Assistant (hass) is present
if pgrep -x "hass" > /dev/null; then
    echo "----------------------------------------------------------------------"
    echo "Terminating Home Assistant ..."
    echo "----------------------------------------------------------------------"
    pkill -x "hass"
    sleep 2
else
    echo "----------------------------------------------------------------------"
    echo "Home Assistant is not running"
    echo "----------------------------------------------------------------------"
    sleep 2
fi
