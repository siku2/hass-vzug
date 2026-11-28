#!/usr/bin/env bash

set -e

cd "$(dirname "$0")/.."

trap 'kill $(jobs -p) 2>/dev/null' EXIT

port=5000
for device in adora_dish_v6000 adora_slq adora_tslq_wp adora_wash_v6000 combair_steamer_v6000_76c; do
    uv run python -m tests.fixtures.start_single_emulator --port "$port" --device_id "$device" &
    port=$((port + 1))
done

wait
