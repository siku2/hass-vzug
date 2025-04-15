#!/bin/bash

echo "----------------------------------------------------------------------"
echo "Terminate processes listing on 5000 and 5001 ..."
echo "----------------------------------------------------------------------"

lsof -i tcp:5000 | awk 'NR!=1 {print $2}' | xargs kill 
lsof -i tcp:5001 | awk 'NR!=1 {print $2}' | xargs kill 
