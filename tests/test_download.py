"""Test di download reale.

    python tests/test_download.py soundcloud CARTELLA
    python tests/test_download.py youtube CARTELLA

Esce con codice 1 se qualcosa non va.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
from downloader import _get_platform, scarica_mp3  # noqa: E402
from piattaforma import trova_eseguibile  # noqa: E402

LINK = {
    # (url, bitrate atteso) — su SoundCloud la fonte è già un MP3 a 128 kbps e viene copiata
    "youtube": ("https://www.youtube.com/watch?v=jNQXAC9IVRw", 320000),
    "soundcloud": ("https://soundcloud.com/jaimemf/youtube-dl-test-video-a-y-baw/s-8Pjrp", 128000),
}

errori = []


def controlla(condizione, messaggio):
    print(("OK   " if condizione else "FAIL ") + messaggio)
    if not condizione:
        errori.append(messaggio)


casi = {
    "https://www.youtube.com/watch?v=x": "youtube", "https://youtu.be/x": "youtube",
    "https://music.youtube.com/watch?v=x": "youtube", "m.youtube.com/watch?v=x": "youtube",
    "  https://soundcloud.com/a/b  ": "soundcloud", "https://on.soundcloud.com/abc": "soundcloud",
    "https://notyoutube.com/x": "unknown", "https://example.com/youtube.com": "unknown", "": "unknown",
}
for u, atteso in casi.items():
    controlla(_get_platform(u) == atteso, f"_get_platform({u!r}) == {atteso!r}")

for nome in ("ffmpeg", "ffprobe", "deno"):
    percorso = trova_eseguibile(nome)
    controlla(percorso is not None, f"{nome} trovato: {percorso}")

if len(sys.argv) >= 3:
    sito, cartella = sys.argv[1], sys.argv[2]
    url, bitrate_atteso = LINK[sito]
    risultato = scarica_mp3(url, directory=cartella, bitrate=320, metadati=True)
    print("Scaricato:", risultato)
    mp3 = Path(risultato)
    controlla(mp3.suffix == ".mp3" and mp3.exists(), "il file MP3 esiste")
    probe = json.loads(subprocess.run(
        [trova_eseguibile("ffprobe"), "-v", "error", "-show_entries",
         "format=bit_rate:format_tags=title,artist:stream=codec_name,codec_type,bit_rate",
         "-of", "json", str(mp3)], capture_output=True, text=True, check=True).stdout)
    print(json.dumps(probe, indent=1, ensure_ascii=False))
    audio = [s for s in probe["streams"] if s["codec_type"] == "audio"]
    copertina = [s for s in probe["streams"] if s["codec_type"] == "video"]
    controlla(audio and audio[0]["codec_name"] == "mp3", "codec audio mp3")
    controlla(audio and int(audio[0].get("bit_rate", 0)) == bitrate_atteso, f"bitrate {bitrate_atteso}")
    controlla(bool(probe["format"].get("tags", {}).get("title")), "tag titolo presente")
    controlla(bool(copertina), "copertina incorporata")
    altri = [p.name for p in mp3.parent.iterdir() if p != mp3]
    controlla(not altri, f"nessun file temporaneo rimasto ({altri})")

print("\nRISULTATO:", "TUTTO OK" if not errori else f"{len(errori)} PROBLEMI")
sys.exit(1 if errori else 0)
