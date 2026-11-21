@echo off
rem Doppio clic per installare (o aggiornare) Audio Downloader.
rem Avvia installer\installa.ps1 leggendolo come UTF-8 (il file non ha BOM per "irm | iex").
title Installazione di Audio Downloader
if not exist "%~dp0installer\installa.ps1" (
    echo.
    echo Prima estrai lo zip: tasto destro sul file .zip, "Estrai tutto",
    echo poi apri la cartella estratta e fai doppio clic su questo file.
    echo.
    pause
    exit /b 1
)
set "AUDIODL_SORGENTE=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& ([scriptblock]::Create([IO.File]::ReadAllText($env:AUDIODL_SORGENTE + 'installer\installa.ps1', [Text.Encoding]::UTF8)))"
echo.
pause
