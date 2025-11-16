
@Echo Off

rem All pip requirements should be installed, but that then requires C++ build tools

rem So run this about 2x
rem py -m pip install pyinstaller

rem And then add the few missing modules:
rem py -m pip install requests 
rem py -m pip install coloredlogs

rem pyinstaller needs to be added manually to the PATH
rem E.g. %localappdata%\Python\pythoncore-3.14-64\Scripts

pyinstaller "%PROJECT_ROOT%/opt/windows_x64/spec/collect_responses.spec" --workpath "%PROJECT_ROOT%/opt/windows_x64/build" --distpath "%PROJECT_ROOT%/dist/windows_x64" --noconfirm 

