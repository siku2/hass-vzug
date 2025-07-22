#!/usr/bin/env bash

# When started as task in VSCode, add necessary path
export PATH="$HOME/.local/bin:$PATH"

set -e

cd "$PROJECT_ROOT"

ruff check . --fix
