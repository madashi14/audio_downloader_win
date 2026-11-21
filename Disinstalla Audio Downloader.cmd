@echo off
rem Doppio clic per disinstallare Audio Downloader (gli MP3 scaricati restano).
rem Si puo' fare anche da Impostazioni > App > App installate.
title Disinstallazione di Audio Downloader
if not exist "%~dp0installer\disinstalla.ps1" (
    echo.
    echo Prima estrai lo zip, oppure disinstalla da Impostazioni, App, App installate.
    echo.
    pause
    exit /b 1
)
choice /c SN /m "Vuoi davvero disinstallare Audio Downloader? Gli MP3 scaricati restano"
if errorlevel 2 exit /b 0
set "AUDIODL_SCRIPT=%~dp0installer\disinstalla.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& ([scriptblock]::Create([IO.File]::ReadAllText($env:AUDIODL_SCRIPT, [Text.Encoding]::UTF8)))"
echo.
pause
