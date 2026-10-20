@echo off
rem Runs at Windows log-in (shortcut in the Startup folder).
rem Waits for the internet, then runs publish.bat so every scheduled article has its bridge link.
rem Results are written to publish_log.txt in this folder.
cd /d "%~dp0"
set "LOG=%~dp0publish_log.txt"
echo.>> "%LOG%"
echo ===== %date% %time% =====>> "%LOG%"
for /l %%i in (1,1,36) do (
  ping -n 1 github.com >nul 2>&1 && goto online
  timeout /t 5 /nobreak >nul
)
echo No internet after 3 minutes, skipped.>> "%LOG%"
exit /b 1
:online
call "%~dp0publish.bat" >> "%LOG%" 2>&1
echo Finished with code %errorlevel%.>> "%LOG%"
