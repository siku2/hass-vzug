#!/bin/bash

###############################################################################
# Since Flask does not support multiple parallel apps, it needs to be done
# at OS/script level
###############################################################################

START_PORT=5000
END_PORT=5004

echo "----------------------------------------------------------------------"
echo "Terminate processes listing on $START_PORT - $END_PORT"
echo "----------------------------------------------------------------------"

for port in $(seq $START_PORT $END_PORT); do
    lsof -i tcp:$port | awk 'NR!=1 {print $2}' | xargs -r kill
done

echo "----------------------------------------------------------------------"
echo "Starting emulators ..."
echo "----------------------------------------------------------------------"

python "$PROJECT_ROOT/tests/fixtures/start_single_emulator.py" --port 5000 --device_id "adora_dish_v6000" &
python "$PROJECT_ROOT/tests/fixtures/start_single_emulator.py" --port 5001 --device_id "adora_slq" & 
python "$PROJECT_ROOT/tests/fixtures/start_single_emulator.py" --port 5002 --device_id "adora_tslq_wp" & 
python "$PROJECT_ROOT/tests/fixtures/start_single_emulator.py" --port 5003 --device_id "adora_wash_v6000" & 
python "$PROJECT_ROOT/tests/fixtures/start_single_emulator.py" --port 5004 --device_id "combair_steamer_v6000_76c" & 

sleep 5

echo "----------------------------------------------------------------------"
echo "Processes listing on $START_PORT - $END_PORT"
for port in $(seq $START_PORT $END_PORT); do
    netstat -nlp | grep ":$port"
done
echo "----------------------------------------------------------------------"

