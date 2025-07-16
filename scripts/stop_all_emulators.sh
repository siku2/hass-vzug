#!/bin/bash

START_PORT=5000
END_PORT=5004

echo "----------------------------------------------------------------------"
echo "Terminate processes listing on $START_PORT - $END_PORT"
echo "----------------------------------------------------------------------"

for port in $(seq $START_PORT $END_PORT); do
    lsof -i tcp:$port | awk 'NR!=1 {print $2}' | xargs -r kill
done
