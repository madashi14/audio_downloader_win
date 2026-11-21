from pathlib import Path
from urllib.parse import urlparse

try:
    import yt_dlp
except ImportError:
    raise SystemExit("Installa yt-dlp: pip install yt-dlp")

from piattaforma import trova_eseguibile

# dominio -> piattaforma (vale anche per i sottodomini: www., m., music., on., ...)
_DOMINI = {
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "youtube-nocookie.com": "youtube",
    "soundcloud.com": "soundcloud",
    "snd.sc": "soundcloud",
}


def _normalizza_url(url):
    url = url.strip()
    if "://" not in url:
        url = "https://" + url
    return url


def _get_platform(url):
    host = (urlparse(_normalizza_url(url)).hostname or "").lower()
    for dominio, piattaforma in _DOMINI.items():
        if host == dominio or host.endswith("." + dominio):
            return piattaforma
    return "unknown"


def scarica_mp3(url, directory=".", bitrate=320, metadati=True,
                progress_hook=None, postprocessor_hook=None, logger=None):
    """Scarica l'audio di un link YouTube/SoundCloud (anche playlist) in MP3.

    progress_hook / postprocessor_hook: callback opzionali di yt-dlp, chiamate
    con un dict durante download e conversione (usate dalla GUI per la barra).
    logger: oggetto con debug/info/warning/error per catturare l'output di yt-dlp.
    Ritorna il percorso dell'MP3, o una lista di percorsi per le playlist.
    """
    url = _normalizza_url(url)
    if _get_platform(url) == "unknown":
        raise ValueError("Piattaforma non supportata: " + url)

    ffmpeg = trova_eseguibile("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg non trovato: riesegui l'installer di Audio Downloader.")

    bitrate = max(32, min(int(bitrate), 320))
    out_dir = Path(directory).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    # yt-dlp scarica l'audio migliore e poi chiama ffmpeg per convertirlo in MP3
    # (libmp3lame al bitrate scelto), cancellando il file originale m4a/webm.
    postprocessors = [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': str(bitrate),
    }]
    if metadati:
        postprocessors += [
            {'key': 'FFmpegMetadata', 'add_metadata': True},  # titolo, artista, data...
            {'key': 'EmbedThumbnail'},                         # copertina nell'MP3
        ]

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': str(out_dir / '%(title)s.%(ext)s'),
        'writethumbnail': metadati,
        'postprocessors': postprocessors,
        'ffmpeg_location': ffmpeg,
        # Forza IPv4 (= --force-ipv4): su alcune reti le connessioni IPv6 verso YouTube
        # restano appese fino al timeout e un download di pochi secondi dura minuti.
        'source_address': '0.0.0.0',
    }
    deno = trova_eseguibile("deno")  # serve a yt-dlp per risolvere le protezioni di YouTube
    if deno:
        ydl_opts['js_runtimes'] = {'deno': {'path': deno}}
    if progress_hook:
        ydl_opts['progress_hooks'] = [progress_hook]
    if postprocessor_hook:
        ydl_opts['postprocessor_hooks'] = [postprocessor_hook]
    if logger:
        ydl_opts['logger'] = logger
        ydl_opts['noprogress'] = True

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    # singolo brano -> [info]; playlist/album -> info['entries']
    entries = info.get('entries') or [info]
    paths = []
    for entry in entries:
        if not entry:
            continue
        # 'filepath' è aggiornato da yt-dlp dopo la conversione: punta al .mp3 finale
        for dl in entry.get('requested_downloads') or []:
            if dl.get('filepath'):
                paths.append(str(Path(dl['filepath']).resolve()))

    if not paths:
        raise RuntimeError("Download fallito per: " + url)

    return paths[0] if len(paths) == 1 else paths
