#!/bin/bash
# pip install pyinstaller

pyinstaller "$PROJECT_ROOT/opt/linux_x64/spec/collect_responses.spec" --workpath "$PROJECT_ROOT/opt/linux_x64/build" --distpath "$PROJECT_ROOT/dist/linux_x64" --noconfirm 


