# Rimuove Audio Downloader da Windows: le icone, la voce in "App installate" e la cartella
# con Python, ffmpeg, Deno, impostazioni e cronologia. Gli MP3 scaricati NON vengono toccati.
#
# Si avvia da Impostazioni > App > App installate > Audio Downloader > Disinstalla,
# con doppio clic su "Disinstalla Audio Downloader.cmd", oppure in PowerShell:
#   powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\AudioDownloader\disinstalla.ps1"
param([switch]$Finestra)   # -Finestra: avviato da Impostazioni, alla fine mostra un messaggio

function Uninstall-AudioDownloader([bool]$ConMessaggio) {
    $ErrorActionPreference = 'Continue'
    $NomeApp = 'Audio Downloader'
    # la copia installata sta dentro la cartella dell'app, accanto a installazione.json
    if ($PSScriptRoot -and (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'installazione.json'))) {
        $Dest = $PSScriptRoot
    } elseif ($env:AUDIODL_DEST) {
        $Dest = $env:AUDIODL_DEST
    } else {
        $Dest = Join-Path $env:LOCALAPPDATA 'AudioDownloader'
    }
    $Dest = $Dest.TrimEnd('\')
    $EnvDir = Join-Path $Dest 'env'
    $info = $null
    $fileInfo = Join-Path $Dest 'installazione.json'
    if (Test-Path -LiteralPath $fileInfo) {
        $info = Get-Content -LiteralPath $fileInfo -Raw -Encoding UTF8 | ConvertFrom-Json
    }

    # chiude l'app se è aperta, altrimenti i suoi file restano bloccati
    Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($EnvDir + '\', [StringComparison]::OrdinalIgnoreCase) } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Start-Sleep -Milliseconds 500 }

    # icone: solo quelle che puntano a questa installazione
    if ($info) {
        $collegamenti = @($info.collegamenti)
    } else {
        $collegamenti = @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs')) |
            Where-Object { $_ } | ForEach-Object { Join-Path $_ "$NomeApp.lnk" }
    }
    $shell = New-Object -ComObject WScript.Shell
    foreach ($lnk in $collegamenti) {
        if ($lnk -and (Test-Path -LiteralPath $lnk)) {
            $destinazione = $shell.CreateShortcut($lnk).TargetPath
            if ($destinazione -and $destinazione.StartsWith($Dest + '\', [StringComparison]::OrdinalIgnoreCase)) {
                Remove-Item -LiteralPath $lnk -Force
                Write-Host "Rimossa l'icona $lnk"
            }
        }
    }

    # voce in "App installate"
    $nomeChiave = if ($info -and $info.chiave_registro) { $info.chiave_registro } else { 'AudioDownloader' }
    $chiave = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$nomeChiave"
    if (Test-Path $chiave) { Remove-Item $chiave -Recurse -Force; Write-Host 'Rimossa da App installate' }

    # impostazioni e cronologia (non in un'installazione di prova, per non toccare quelle vere)
    $dati = Join-Path $env:APPDATA 'AudioDownloader'
    if ($nomeChiave -eq 'AudioDownloader' -and (Test-Path -LiteralPath $dati)) {
        Remove-Item -LiteralPath $dati -Recurse -Force
        Write-Host 'Rimosse impostazioni e cronologia'
    }

    # cartella del programma (rmdir è molto più veloce di Remove-Item con migliaia di file)
    Set-Location -LiteralPath $env:USERPROFILE   # non si può cancellare la cartella in cui ci si trova
    for ($tentativo = 1; $tentativo -le 3 -and (Test-Path -LiteralPath $Dest); $tentativo++) {
        cmd.exe /d /c "rmdir /s /q `"$Dest`"" 2>$null
        if (Test-Path -LiteralPath $Dest) { Start-Sleep -Seconds 2 }
    }

    if (Test-Path -LiteralPath $Dest) {
        $messaggio = "Quasi fatto: non sono riuscito a cancellare la cartella $Dest. Riavvia il PC e cancellala a mano."
        Write-Host $messaggio -ForegroundColor Yellow
    } else {
        Write-Host "Rimossa $Dest"
        $messaggio = "$NomeApp è stato disinstallato. I tuoi MP3 sono rimasti dove li avevi salvati."
        Write-Host ''
        Write-Host $messaggio -ForegroundColor Green
    }
    if ($ConMessaggio) {
        $shell.Popup($messaggio, 0, $NomeApp, 64) | Out-Null
    }
}

Uninstall-AudioDownloader $Finestra.IsPresent
