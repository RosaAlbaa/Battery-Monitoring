@echo off
setlocal
python -m pip install -r requirements-dev.txt || exit /b 1
python -m pytest -q tests || exit /b 1
for /f %%v in ('python -c "import battery_monitoring; print(battery_monitoring.__version__)"') do set VER=%%v
pyinstaller --noconfirm --clean --windowed --onedir --name BatteryMonitoring --icon assets\battery_monitoring.ico --hidden-import pystray._win32 battery_monitoring.pyw || exit /b 1
set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if exist "%ISCC%" (
    "%ISCC%" /DAppVersion=%VER% installer\battery_monitoring.iss || exit /b 1
    echo.
    echo Installer: dist\BatteryMonitoring-Setup-%VER%.exe
) else (
    echo.
    echo Inno Setup not found, skipped the installer. App: dist\BatteryMonitoring\BatteryMonitoring.exe
)
