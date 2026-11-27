#!/usr/bin/env bash

set -e

cd "$(dirname "$0")/.."

if ! command -v uv >/dev/null; then
    python3 -m pip install --user uv
    export PATH="$HOME/.local/bin:$PATH"
fi

uv sync
