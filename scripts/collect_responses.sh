#!/usr/bin/env bash

cd "$(dirname "$0")/.."

uv run python -m tests.fixtures.collect_responses "$@"
