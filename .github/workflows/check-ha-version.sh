#!/usr/bin/env bash
set -euo pipefail

hacs_req=$(yq -r -oj .homeassistant hacs.json)
project_req=$(yq -p toml -oy '.project.dependencies[]' pyproject.toml | sed -n 's/^homeassistant==\([0-9.]*\)$/\1/p')

if [ "$hacs_req" != "$project_req" ]; then
	echo "::error file=hacs.json::HACS version requirement for HA doesn't match requirement from pyproject.toml"
	exit 1
fi
