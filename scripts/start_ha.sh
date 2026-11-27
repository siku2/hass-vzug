#!/usr/bin/env bash

set -e

cd "$(dirname "$0")/.."

PYTHONPATH="$PWD" exec uv run hass --config config --debug
