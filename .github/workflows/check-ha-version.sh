#!/usr/bin/env bash
set -euo pipefail

hacs_req=$(yq -r -oj .homeassistant hacs.json)
requirements_req=$(sed -n 's/^homeassistant==\([0-9.]*\)$/\1/p' requirements.txt)

if [ "$hacs_req" != "$requirements_req" ]; then
	echo "::error file=hacs.json::HACS version requirement for HA doesn't match requirement from requirements.txt"
	exit 1
fi
