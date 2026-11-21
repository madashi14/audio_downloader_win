"""Tutto ciò che cambia tra macOS e Windows, in un solo posto."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

MAC = sys.platform == "darwin"
WINDOWS = os.name == "nt"


def cartella_dati():
    """Dove salvare impostazioni e log dell'app."""
    if MAC:
        base = Path.home() / "Library" / "Application Support"
    elif WINDOWS:
        base = Path(os.environ.get("APPDATA") or Path.home())
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "AudioDownloader"


def apri(percorso):
    """Apre un file o una cartella con l'app predefinita del sistema."""
    if WINDOWS:
        os.startfile(str(percorso))
    elif MAC:
        subprocess.Popen(["open", str(percorso)])
    else:
        subprocess.Popen(["xdg-open", str(percorso)])


def mostra_nel_file_manager(percorso):
    """Apre il Finder / Esplora file con il file selezionato."""
    if WINDOWS:
        subprocess.Popen(f'explorer /select,"{percorso}"')
    elif MAC:
        subprocess.Popen(["open", "-R", str(percorso)])
    else:
        apri(Path(percorso).parent)


def _cartelle_python():
    """Cartelle del Python che sta girando: qui l'installer mette ffmpeg e Deno."""
    py = Path(sys.executable).resolve().parent
    return [py, Path(sys.prefix) / "bin", Path(sys.prefix) / "Library" / "bin", Path(sys.prefix) / "Scripts"]


def _cartelle_extra():
    """Altri posti dove di solito finiscono ffmpeg/deno installati a mano.

    Le app del Mac aperte dal Finder o dal Dock non ricevono il PATH del Terminale,
    quindi gli strumenti installati (da Homebrew o winget) vanno cercati a mano.
    """
    cartelle = []
    if MAC:
        cartelle += [Path("/opt/homebrew/bin"), Path("/usr/local/bin"), Path.home() / ".deno" / "bin"]
    if WINDOWS:
        winget = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet"
        cartelle.append(winget / "Links")
        if (winget / "Packages").is_dir():
            cartelle += sorted(p for p in (winget / "Packages").glob("*") if p.is_dir())
    return cartelle


def trova_eseguibile(nome):
    """Percorso completo di un programma (es. 'ffmpeg', 'deno'), o None se non c'è.

    Prima quelli installati insieme all'app (un altro ffmpeg nel PATH potrebbe non
    saper creare MP3), poi il PATH, poi gli altri posti noti.
    """
    estensioni = [".exe", ""] if WINDOWS else [""]

    def cerca(cartelle):
        for cartella in cartelle:
            for ext in estensioni:
                candidato = cartella / (nome + ext)
                if candidato.is_file() and os.access(candidato, os.X_OK):
                    return str(candidato)
        return None

    return cerca(_cartelle_python()) or shutil.which(nome) or cerca(_cartelle_extra())
