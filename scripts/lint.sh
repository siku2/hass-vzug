#!/usr/bin/env bash

set -e

cd "$PROJECT_ROOT"

ruff check . --fix
