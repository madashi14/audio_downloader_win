"""Controllo finale dell'installer: Python, librerie, ffmpeg e Deno funzionano?

Cerca ffmpeg e Deno con la stessa funzione che usa l'app, così se qualcosa manca
l'installer lo dice subito invece di farlo scoprire al primo download.
Uso: python controlla.py <cartella dell'app>
"""
import subprocess
import sys

sys.path.insert(0, sys.argv[1])

problemi = []

try:
    import customtkinter  # noqa: F401
    import PIL  # noqa: F401
    import tkinter
    import yt_dlp

    tkinter.Tcl()  # carica Tcl: senza i suoi file l'interfaccia non si aprirebbe
    print("Python", sys.version.split()[0], "- yt-dlp", yt_dlp.version.__version__)
except Exception as e:  # noqa: BLE001
    problemi.append(f"librerie Python: {e}")

from piattaforma import trova_eseguibile  # noqa: E402

ffmpeg = trova_eseguibile("ffmpeg")
if not ffmpeg:
    problemi.append("ffmpeg non trovato")
else:
    encoder = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    if "libmp3lame" not in encoder:
        problemi.append("ffmpeg non sa creare MP3 (manca libmp3lame)")
    print("ffmpeg:", ffmpeg)

deno = trova_eseguibile("deno")
if not deno:
    problemi.append("Deno non trovato")
else:
    versione = subprocess.run([deno, "--version"], capture_output=True, text=True)
    if versione.returncode != 0:
        problemi.append("Deno non parte")
    print("deno:", deno, "-", (versione.stdout.splitlines() or ["?"])[0])

if problemi:
    print("Problemi:", "; ".join(problemi))
    sys.exit(1)
print("Tutto a posto.")
