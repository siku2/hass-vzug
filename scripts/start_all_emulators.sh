#!/bin/bash

###############################################################################
# Since Flask does not support multiple parallel apps, it needs to be done
# at OS/script level
###############################################################################

echo "----------------------------------------------------------------------"
echo "Terminate processes listing on 5000 and 5001 ..."
echo "----------------------------------------------------------------------"

lsof -i tcp:5000 | awk 'NR!=1 {print $2}' | xargs kill 
lsof -i tcp:5001 | awk 'NR!=1 {print $2}' | xargs kill 

echo "----------------------------------------------------------------------"
echo "Starting emulators on 5000 and 5001 ..."
echo "----------------------------------------------------------------------"

python "$PROJECT_ROOT/tests/fixtures/start_single_emulator.py" --port 5000 --device_id "adora_slq" & 
python "$PROJECT_ROOT/tests/fixtures/start_single_emulator.py" --port 5001 --device_id "adora_tslq_wp" & 

sleep 5

echo "----------------------------------------------------------------------"
echo "Processes listing on 5000 and 5001"
netstat -nlp | grep :5000
netstat -nlp | grep :5001
echo "----------------------------------------------------------------------"

