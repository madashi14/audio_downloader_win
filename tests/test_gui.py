"""Pilota l'interfaccia grafica come farebbe una persona e salva degli screenshot.

    python tests/test_gui.py CARTELLA_DOWNLOAD CARTELLA_SCREENSHOT [URL_DOWNLOAD] [URL_LUNGO]

Le impostazioni vengono salvate in una cartella temporanea (non tocca quelle vere)
e gli appunti sono finti. Esce con codice 1 se un controllo fallisce.
"""
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import customtkinter as ctk  # noqa: E402

import gui  # noqa: E402
from piattaforma import MAC  # noqa: E402

DL = Path(sys.argv[1])
SHOTS = Path(sys.argv[2])
URL = sys.argv[3] if len(sys.argv) > 3 else "https://soundcloud.com/jaimemf/youtube-dl-test-video-a-y-baw/s-8Pjrp"
URL_LUNGO = sys.argv[4] if len(sys.argv) > 4 else "https://www.youtube.com/watch?v=aqz-KE-bpKQ"
SHOTS.mkdir(parents=True, exist_ok=True)

tmp = Path(tempfile.mkdtemp())
gui.DATA_DIR = tmp
gui.SETTINGS_FILE = tmp / "settings.json"
gui.ERROR_LOG = tmp / "errori.log"

errori = []


def controlla(condizione, messaggio):
    print(("OK   " if condizione else "FAIL ") + messaggio, flush=True)
    if not condizione:
        errori.append(messaggio)


gui._prepara_sistema()
ctk.set_appearance_mode("light")
app = gui.AudioDownloaderApp()
app.clipboard_get = lambda: URL  # finti appunti
app.dir_var.set(str(DL / "principale"))


def pump(sec=0.3):
    t0 = time.time()
    while time.time() - t0 < sec:
        app.update()
        time.sleep(0.02)


def run_until(cond, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        app.update()
        if cond():
            return True
        time.sleep(0.03)
    return False


def shot(nome):
    app.lift()
    app.attributes("-topmost", True)
    pump(0.8)
    file = SHOTS / f"{nome}.png"
    if MAC:
        subprocess.run(["screencapture", "-x", str(file)], check=False)
    else:
        from PIL import ImageGrab
        x, y, w, h = app.winfo_rootx(), app.winfo_rooty(), app.winfo_width(), app.winfo_height()
        ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).save(file)
    print("[screenshot]", file.name, flush=True)


def finito():
    return not app._in_corso() and app.coda.empty()


def stato():
    return app.stato_titolo.cget("text"), app.stato_dettaglio.cget("text")


pump(1.5)
controlla(app.url_var.get() == URL, "incolla automatico del link dagli appunti")
shot("1_avvio_chiaro")

app.url_var.set("https://example.com/video")
pump()
controlla("non supportato" in app.badge_hint.cget("text"), "link non supportato riconosciuto")

app.url_var.set(URL)
pump()
app._avvia()
ok = run_until(finito, 300)
pump(0.5)
print("stato:", stato())
controlla(ok and "Fatto" in stato()[0], "download completato dall'interfaccia")
file_scaricati = list((DL / "principale").glob("*.mp3"))
controlla(len(file_scaricati) == 1, f"un MP3 nella cartella ({[p.name for p in file_scaricati]})")
controlla(len(app.righe) == 1, "brano aggiunto alla cronologia")
app._autoincolla()
controlla(app.url_var.get() == "", "dopo il download il link non viene riproposto")
shot("2_fatto_chiaro")

app._cambia_tema()
shot("3_fatto_scuro")

# annullamento con un video lungo (su YouTube può fallire dai server di GitHub: non è bloccante)
app.dir_var.set(str(DL / "annulla"))
app.url_var.set(URL_LUNGO)
app._avvia()
partito = run_until(lambda: app.stato_pct.cget("text") != "" or not app._in_corso(), 120)
app._annulla()
ok = run_until(finito, 120)
pump(0.5)
print("stato annullamento:", stato())
if "annullato" in stato()[0].lower():
    rimasti = list((DL / "annulla").iterdir()) if (DL / "annulla").exists() else []
    controlla(not rimasti, f"nessun file rimasto dopo l'annullamento ({[p.name for p in rimasti]})")
else:
    print("AVVISO: annullamento non verificato (download non partito):", stato())
shot("4_annullato_scuro")

app.url_var.set("https://www.youtube.com/watch?v=aaaaaaaaaaa")
app._avvia()
ok = run_until(finito, 120)
pump(0.5)
print("stato errore:", stato())
controlla(ok and "storto" in stato()[0], "errore mostrato nell'interfaccia")
shot("5_errore_scuro")

log = gui.ERROR_LOG.read_text(encoding="utf-8") if gui.ERROR_LOG.exists() else ""
controlla(not log, "nessun errore interno dell'interfaccia" + (f":\n{log}" if log else ""))
app._chiudi()

print("\nRISULTATO:", "TUTTO OK" if not errori else f"{len(errori)} PROBLEMI")
sys.exit(1 if errori else 0)
