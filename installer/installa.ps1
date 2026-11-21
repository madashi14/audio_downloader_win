# Installa (o aggiorna) Audio Downloader su Windows.
#
# Non servono permessi di amministratore e non tocca il resto del PC:
# Python, ffmpeg, Deno e l'app finiscono in %LOCALAPPDATA%\AudioDownloader,
# l'icona "Audio Downloader" va sul Desktop e nel menu Start, e l'app compare
# in Impostazioni > App > App installate (da dove si disinstalla).
#
# Uso, in PowerShell:
#   irm https://raw.githubusercontent.com/madashi14/audio_downloader_win/main/installer/installa.ps1 | iex
# oppure doppio clic su "Installa Audio Downloader.cmd" nella cartella scaricata.
#
# Variabili per le prove: AUDIODL_DEST (cartella di installazione), AUDIODL_COLLEGAMENTI
# (cartella per le icone al posto di Desktop e Start), AUDIODL_NON_APRIRE=1 (non apre
# l'app alla fine), AUDIODL_REF (ramo o commit da scaricare da GitHub).
#
# Nota: il file è salvato senza BOM, che con "irm | iex" verrebbe letto come un comando.

# Tutto dentro una funzione: con "irm | iex" lo script arriva per intero prima di partire
# e le sue variabili non restano nella finestra di PowerShell di chi lo lancia.
function Install-AudioDownloader {
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'   # senza barra Invoke-WebRequest è molto più veloce
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

    $Repo = 'madashi14/audio_downloader_win'
    $Ref = if ($env:AUDIODL_REF) { $env:AUDIODL_REF } else { 'main' }
    $NomeApp = 'Audio Downloader'
    $Versione = '1.0'
    $Dest = if ($env:AUDIODL_DEST) { $env:AUDIODL_DEST } else { Join-Path $env:LOCALAPPDATA 'AudioDownloader' }
    $EnvDir = Join-Path $Dest 'env'
    $AppFiles = Join-Path $Dest 'app'
    $Mamba = Join-Path $Dest 'bin\micromamba.exe'
    $RootMamba = Join-Path $Dest 'mamba'
    $Python = Join-Path $EnvDir 'python.exe'
    $PythonW = Join-Path $EnvDir 'pythonw.exe'
    $Gui = Join-Path $AppFiles 'gui.py'
    # un'installazione di prova ha una sua voce in "App installate", separata da quella vera
    $ChiaveRegistro = if ($env:AUDIODL_DEST) { 'AudioDownloader-Prova' } else { 'AudioDownloader' }
    $TmpSorgente = $null
    $Fallito = $false
    # cache dei pacchetti di micromamba (il comando "clean" la trova solo tramite questa variabile);
    # il valore precedente viene ripristinato alla fine
    $RootMambaPrima = $env:MAMBA_ROOT_PREFIX
    $env:MAMBA_ROOT_PREFIX = $RootMamba

    function Titolo([string]$Testo) {
        Write-Host ''
        Write-Host '==> ' -ForegroundColor Magenta -NoNewline
        Write-Host $Testo -ForegroundColor White
    }

    # Avvia un programma esterno e si ferma se fallisce (PowerShell 5 non lo fa da solo).
    # L'output di errore viene mostrato come testo normale, non come errore di PowerShell.
    function Esegui([string]$Messaggio, [string]$Exe, [string[]]$Argomenti) {
        $ErrorActionPreference = 'Continue'
        & $Exe @Argomenti 2>&1 | ForEach-Object { "$_" } | Out-Host
        if ($LASTEXITCODE -ne 0) { throw $Messaggio }
    }

    # Un'app aperta blocca i suoi file: va chiusa prima di aggiornarla.
    function Chiudi-App {
        Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($EnvDir + '\', [StringComparison]::OrdinalIgnoreCase) } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Start-Sleep -Milliseconds 500 }
    }

    try {
        Write-Host ''
        Write-Host "Installazione di $NomeApp" -ForegroundColor White
        Write-Host 'Ci vorranno alcuni minuti e circa 1 GB di spazio libero (alla fine ne restano occupati circa 600 MB).'
        Write-Host 'Non servono permessi di amministratore.'
        if (-not [Environment]::Is64BitOperatingSystem) { throw 'serve Windows a 64 bit.' }
        Chiudi-App

        # ------------------------------------------------------------------ 1
        Titolo "1/5  Preparo i file dell'app"
        $Sorgente = $null
        $candidati = @($env:AUDIODL_SORGENTE)
        if ($PSScriptRoot) { $candidati += (Split-Path $PSScriptRoot -Parent) }
        foreach ($c in $candidati) {
            if ($c -and (Test-Path -LiteralPath (Join-Path $c 'app\gui.py'))) { $Sorgente = (Resolve-Path -LiteralPath $c).Path; break }
        }
        if ($Sorgente) {
            Write-Host "Uso i file della cartella: $Sorgente"
        } else {
            $TmpSorgente = Join-Path ([IO.Path]::GetTempPath()) ('AudioDownloader-' + [guid]::NewGuid().ToString('N'))
            New-Item -ItemType Directory -Path $TmpSorgente | Out-Null
            $zip = Join-Path $TmpSorgente 'sorgente.zip'
            Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/$Repo/archive/$Ref.zip" -OutFile $zip
            Expand-Archive -LiteralPath $zip -DestinationPath $TmpSorgente
            $Sorgente = (Get-ChildItem -LiteralPath $TmpSorgente -Directory | Select-Object -First 1).FullName
            Write-Host "Scaricati da github.com/$Repo"
        }

        # ------------------------------------------------------------------ 2
        Titolo '2/5  Scarico micromamba (gestisce Python e ffmpeg)'
        New-Item -ItemType Directory -Force -Path (Split-Path $Mamba) | Out-Null
        if (-not (Test-Path -LiteralPath $Mamba)) {
            Invoke-WebRequest -UseBasicParsing -OutFile "$Mamba.tmp" `
                -Uri 'https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-win-64'
            Move-Item -LiteralPath "$Mamba.tmp" -Destination $Mamba -Force
        }
        Esegui 'micromamba non funziona.' $Mamba @('--version')

        # ------------------------------------------------------------------ 3
        Titolo '3/5  Installo Python, ffmpeg e le librerie (è la parte più lunga)'
        $azione = if (Test-Path -LiteralPath (Join-Path $EnvDir 'conda-meta')) { 'install' } else { 'create' }
        Esegui "l'installazione di Python e ffmpeg non è riuscita." $Mamba @(
            $azione, '--yes', '--prefix', $EnvDir,
            '--channel', 'conda-forge', '--override-channels', 'python=3.12', 'tk', 'ffmpeg', 'pip')
        Write-Host "Installo yt-dlp, Deno e l'interfaccia grafica..."
        Esegui "l'installazione delle librerie Python non è riuscita." $Python @(
            '-m', 'pip', 'install', '--quiet', '--disable-pip-version-check', '--no-cache-dir',
            '--no-warn-script-location', '--upgrade', 'yt-dlp[default]', 'customtkinter', 'pillow', 'deno')
        # i pacchetti scaricati non servono più: circa 500 MB liberati
        Write-Host 'Libero lo spazio occupato dai pacchetti scaricati...'
        & { $ErrorActionPreference = 'Continue'; & $Mamba clean --all --yes 2>&1 | Out-Null }

        # ------------------------------------------------------------------ 4
        Titolo "4/5  Copio l'app"
        if (Test-Path -LiteralPath $AppFiles) { Remove-Item -LiteralPath $AppFiles -Recurse -Force }
        Copy-Item -LiteralPath (Join-Path $Sorgente 'app') -Destination $AppFiles -Recurse
        Get-ChildItem -LiteralPath $AppFiles -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force
        # il disinstallatore viene salvato con BOM: così PowerShell 5 legge bene le lettere accentate
        $testo = [IO.File]::ReadAllText((Join-Path $Sorgente 'installer\disinstalla.ps1'), [Text.Encoding]::UTF8)
        [IO.File]::WriteAllText((Join-Path $Dest 'disinstalla.ps1'), $testo, (New-Object Text.UTF8Encoding $true))
        # controlla Python, librerie, ffmpeg e Deno esattamente come li cercherà l'app:
        # se qualcosa manca meglio dirlo adesso che al primo download
        Esegui 'qualcosa non si è installato correttamente (vedi sopra).' $Python @(
            (Join-Path $Sorgente 'installer\controlla.py'), $AppFiles)

        # ------------------------------------------------------------------ 5
        Titolo '5/5  Creo le icone sul Desktop e nel menu Start'
        if ($env:AUDIODL_COLLEGAMENTI) {
            New-Item -ItemType Directory -Force -Path $env:AUDIODL_COLLEGAMENTI | Out-Null
            $cartelle = @($env:AUDIODL_COLLEGAMENTI)
        } else {
            $cartelle = @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs')) | Where-Object { $_ }
        }
        $shell = New-Object -ComObject WScript.Shell
        $collegamenti = @()
        foreach ($cartella in $cartelle) {
            $percorso = Join-Path $cartella "$NomeApp.lnk"
            $lnk = $shell.CreateShortcut($percorso)
            $lnk.TargetPath = $PythonW
            $lnk.Arguments = '"' + $Gui + '"'
            $lnk.WorkingDirectory = $AppFiles
            $lnk.IconLocation = (Join-Path $AppFiles 'assets\icon.ico') + ',0'
            $lnk.Description = "Scarica l'audio di YouTube e SoundCloud in MP3"
            $lnk.Save()
            $collegamenti += $percorso
            Write-Host "Icona creata: $percorso"
        }

        # voce in Impostazioni > App > App installate (solo per questo utente, niente admin)
        $chiave = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$ChiaveRegistro"
        New-Item -Path $chiave -Force | Out-Null
        $kb = [int]((Get-ChildItem -LiteralPath $Dest -Recurse -File -Force -ErrorAction SilentlyContinue |
            Measure-Object -Property Length -Sum).Sum / 1KB)
        $testi = [ordered]@{
            DisplayName     = $NomeApp
            DisplayVersion  = $Versione
            Publisher       = 'madashi14'
            DisplayIcon     = Join-Path $AppFiles 'assets\icon.ico'
            InstallLocation = $Dest
            URLInfoAbout    = "https://github.com/$Repo"
            UninstallString = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $Dest 'disinstalla.ps1') + '" -Finestra'
        }
        foreach ($nome in $testi.Keys) {
            New-ItemProperty -Path $chiave -Name $nome -Value $testi[$nome] -PropertyType String -Force | Out-Null
        }
        foreach ($nome in 'NoModify', 'NoRepair') {
            New-ItemProperty -Path $chiave -Name $nome -Value 1 -PropertyType DWord -Force | Out-Null
        }
        New-ItemProperty -Path $chiave -Name 'EstimatedSize' -Value $kb -PropertyType DWord -Force | Out-Null

        # cosa togliere alla disinstallazione
        $info = [ordered]@{ versione = $Versione; collegamenti = $collegamenti; chiave_registro = $ChiaveRegistro }
        [IO.File]::WriteAllText((Join-Path $Dest 'installazione.json'), ($info | ConvertTo-Json), (New-Object Text.UTF8Encoding $false))

        Write-Host ''
        Write-Host 'Fatto! ' -ForegroundColor Green -NoNewline
        Write-Host "Trovi `"$NomeApp`" sul Desktop e nel menu Start ($([math]::Round($kb / 1KB)) MB)."
        Write-Host 'Per aggiornarla rilancia lo stesso comando.'
        Write-Host 'Per toglierla: Impostazioni > App > App installate > Audio Downloader > Disinstalla.'
        if (-not $env:AUDIODL_NON_APRIRE) {
            Start-Process -FilePath $PythonW -ArgumentList ('"' + $Gui + '"') -WorkingDirectory $AppFiles
        }
    }
    catch {
        $Fallito = $true
        Write-Host ''
        Write-Host 'Errore: ' -ForegroundColor Red -NoNewline
        Write-Host $_.Exception.Message
        Write-Host "L'installazione non è andata a buon fine. Controlla la connessione a internet e riprova;"
        Write-Host 'se il problema resta, manda uno screenshot di questa finestra.'
    }
    finally {
        $env:MAMBA_ROOT_PREFIX = $RootMambaPrima
        if ($TmpSorgente -and (Test-Path -LiteralPath $TmpSorgente)) {
            Remove-Item -LiteralPath $TmpSorgente -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    # codice di uscita 1 solo se lanciato come file (con "irm | iex" chiuderebbe la finestra)
    if ($Fallito -and $PSCommandPath) { exit 1 }
}

Install-AudioDownloader
