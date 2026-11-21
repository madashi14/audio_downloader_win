"""Audio Downloader: interfaccia grafica per scaricare MP3 da YouTube e SoundCloud."""
import json
import queue
import re
import threading
import time
import traceback
from pathlib import Path
from tkinter import TclError, filedialog
from tkinter import font as tkfont

import customtkinter as ctk
import yt_dlp
from PIL import Image, ImageTk

from downloader import _get_platform, scarica_mp3
from piattaforma import MAC, WINDOWS, apri, cartella_dati, mostra_nel_file_manager

APP_NAME = "Audio Downloader"
BASE = Path(__file__).resolve().parent
ASSETS = BASE / "assets"
DATA_DIR = cartella_dati()
SETTINGS_FILE = DATA_DIR / "settings.json"
ERROR_LOG = DATA_DIR / "errori.log"

# Palette (chiaro, scuro)
ACCENT = ("#7C3AED", "#8B5CF6")
ACCENT_HOVER = ("#6D28D9", "#7C3AED")
ACCENT_SOFT = ("#EDE7FE", "#2C2445")
BG = ("#F4F2FA", "#111018")
CARD = ("#FFFFFF", "#1B1A24")
CARD_BORDER = ("#E7E3F3", "#2A2836")
FIELD = ("#F7F5FC", "#24222F")
FIELD_HOVER = ("#ECE8F7", "#2F2C3D")
TEXT = ("#1C1A26", "#F2F0FA")
MUTED = ("#6B6880", "#9A97AD")
SUCCESS = ("#15803D", "#4ADE80")
ERROR = ("#DC2626", "#F87171")
DANGER = ("#E11D48", "#E11D48")
DANGER_HOVER = ("#BE123C", "#BE123C")

PIATTAFORME = {
    "youtube": ("YouTube", "#FF0033"),
    "soundcloud": ("SoundCloud", "#FF5500"),
}
BITRATES = ["128", "192", "256", "320"]
FASI_CONVERSIONE = {
    "ExtractAudio": "Conversione in MP3…",
    "Metadata": "Aggiunta di titolo e artista…",
    "ThumbnailsConvertor": "Preparazione copertina…",
    "EmbedThumbnail": "Aggiunta copertina…",
}
MAX_CRONOLOGIA = 30


class Annullato(yt_dlp.utils.DownloadCancelled):
    msg = "Download annullato"


class _LoggerSilenzioso:
    """Tiene yt-dlp zitto (con pythonw non c'è console); gli errori arrivano come eccezioni."""

    def debug(self, msg):
        pass

    info = warning = error = debug


ERRORI_NOTI = [  # (frammento del messaggio di yt-dlp, spiegazione in italiano)
    ("Private video", "Il video è privato."),
    ("not a bot", "YouTube chiede di dimostrare che non sei un robot: riprova tra un po' "
                  "o da un'altra connessione (succede con VPN e reti condivise)."),
    ("video is unavailable", "Il video non è disponibile: rimosso, privato o link sbagliato."),
    ("Video unavailable", "Il video non è disponibile: rimosso, privato o link sbagliato."),
    ("confirm your age", "Il video ha limiti di età e richiede l'accesso a YouTube."),
    ("not available in your country", "Il contenuto non è disponibile nel tuo paese."),
    ("HTTP Error 404", "Contenuto non trovato (errore 404): controlla il link."),
    ("Unable to download webpage", "Impossibile raggiungere il sito: controlla la connessione."),
    ("timed out", "La connessione è scaduta: controlla la connessione e riprova."),
    ("ffmpeg not found", "ffmpeg non trovato: installalo e assicurati che sia nel PATH."),
]


def _pulisci_errore(exc):
    msg = re.sub(r"\x1b\[[0-9;]*m", "", str(exc)).strip()
    msg = re.sub(r"^(ERROR:\s*)+", "", msg)
    for frammento, spiegazione in ERRORI_NOTI:
        if frammento.lower() in msg.lower():
            return spiegazione
    msg = re.sub(r"^\[[^\]]+\]\s*[^\s:]+:\s*", "", msg)  # toglie "[youtube] abc123: "
    return msg or exc.__class__.__name__


def _formatta_mb(n):
    return f"{n / 1_048_576:.1f} MB".replace(".", ",")


def _formatta_eta(sec):
    sec = int(sec)
    return f"{sec // 60}:{sec % 60:02d}"


def _tronca(testo, n):
    return testo if len(testo) <= n else testo[: n - 1] + "…"


def _cartella_musica_default():
    musica = Path.home() / "Music"
    return str(musica if musica.is_dir() else Path.home())


class AudioDownloaderApp(ctk.CTk):
    def __init__(self):
        self.settings = self._carica_settings()
        ctk.set_appearance_mode(self.settings.get("tema", "system"))
        super().__init__(fg_color=BG)

        self.title(APP_NAME)
        self._famiglia_font = "Segoe UI" if WINDOWS else tkfont.nametofont("TkDefaultFont").actual("family")
        self._imposta_icona()
        self._dimensiona_finestra(640, 800)
        self.minsize(540, 660)

        self.coda = queue.Queue()
        self.annulla = threading.Event()
        self.worker = None
        self._ultimo_tmp = None
        self._link_gia_visti = set()  # link già proposti dagli appunti o già scaricati
        self._visti = set()

        self.url_var = ctk.StringVar()
        self.dir_var = ctk.StringVar(value=self.settings.get("cartella") or _cartella_musica_default())
        self.metadati_var = ctk.BooleanVar(value=self.settings.get("metadati", True))

        self._costruisci_ui()
        self._carica_cronologia()

        self.url_var.trace_add("write", lambda *_: self._aggiorna_badge())
        self.bind("<FocusIn>", self._autoincolla)
        self.protocol("WM_DELETE_WINDOW", self._chiudi)
        self.after(100, self._leggi_coda)
        self.after(300, self._all_avvio)

    def _all_avvio(self):
        self._porta_in_primo_piano()
        self.url_entry.focus_set()
        # controlla subito gli appunti: su Mac la finestra può aprirsi senza ricevere il focus
        self._autoincolla()

    def _porta_in_primo_piano(self):
        if MAC:
            try:
                from AppKit import NSApplication
                app = NSApplication.sharedApplication()
                if hasattr(app, "activate"):          # macOS 14+
                    app.activate()
                else:
                    app.activateIgnoringOtherApps_(True)
            except Exception:
                pass
        self.lift()
        try:
            self.focus_force()
        except TclError:
            pass

    # ------------------------------------------------------------------ UI
    def _font(self, size, weight="normal"):
        return ctk.CTkFont(family=self._famiglia_font, size=size, weight=weight)

    def _imposta_icona(self):
        try:
            if WINDOWS and (ASSETS / "icon.ico").exists():
                self.iconbitmap(str(ASSETS / "icon.ico"))
            elif (ASSETS / "icon.png").exists():
                # su Mac questo imposta anche l'icona nel Dock
                img = Image.open(ASSETS / "icon.png").resize((256, 256), Image.LANCZOS)
                self._icona_tk = ImageTk.PhotoImage(img, master=self)
                self.iconphoto(True, self._icona_tk)
        except (TclError, OSError):
            pass

    def _dimensiona_finestra(self, w, h):
        try:
            scala = self._get_window_scaling()
        except Exception:
            scala = 1.0
        sw = self.winfo_screenwidth() / scala
        sh = self.winfo_screenheight() / scala
        h = int(min(h, sh - 90))
        x, y = int((sw - w) / 2), int(max(20, (sh - h) / 2 - 20))
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _sezione(self, master, testo):
        return ctk.CTkLabel(master, text=testo, font=self._font(11, "bold"),
                            text_color=MUTED, height=18, anchor="w")

    def _bottone_secondario(self, master, testo, comando, width=88, height=44):
        return ctk.CTkButton(master, text=testo, command=comando, width=width, height=height,
                             corner_radius=12, fg_color=FIELD, hover_color=FIELD_HOVER,
                             text_color=TEXT, border_width=1, border_color=CARD_BORDER,
                             font=self._font(13, "bold"))

    def _card(self, master):
        return ctk.CTkFrame(master, fg_color=CARD, corner_radius=18,
                            border_width=1, border_color=CARD_BORDER)

    def _costruisci_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1)
        px = 24

        # --- Intestazione
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=px, pady=(22, 14))
        header.grid_columnconfigure(1, weight=1)
        logo_png = ASSETS / "icon.png"
        if logo_png.exists():
            img = Image.open(logo_png)
            self._logo = ctk.CTkImage(light_image=img, dark_image=img, size=(46, 46))
            ctk.CTkLabel(header, image=self._logo, text="").grid(row=0, column=0, rowspan=2, padx=(0, 14))
        ctk.CTkLabel(header, text=APP_NAME, font=self._font(24, "bold"), text_color=TEXT,
                     anchor="w", height=30).grid(row=0, column=1, sticky="sw")
        ctk.CTkLabel(header, text="Da YouTube e SoundCloud a MP3, in un clic", font=self._font(13),
                     text_color=MUTED, anchor="w", height=18).grid(row=1, column=1, sticky="nw")
        self.tema_btn = ctk.CTkButton(header, text="", width=40, height=40, corner_radius=20,
                                      fg_color=FIELD, hover_color=FIELD_HOVER, text_color=TEXT,
                                      font=self._font(17), command=self._cambia_tema)
        self.tema_btn.grid(row=0, column=2, rowspan=2)
        self._aggiorna_icona_tema()

        # --- Card opzioni
        card = self._card(self)
        card.grid(row=1, column=0, sticky="ew", padx=px)
        card.grid_columnconfigure(0, weight=1)
        ip = 20

        self._sezione(card, "LINK").grid(row=0, column=0, sticky="w", padx=ip, pady=(18, 6))
        riga_url = ctk.CTkFrame(card, fg_color="transparent")
        riga_url.grid(row=1, column=0, sticky="ew", padx=ip)
        riga_url.grid_columnconfigure(0, weight=1)
        self.url_entry = ctk.CTkEntry(
            riga_url, textvariable=self.url_var, height=44, corner_radius=12,
            fg_color=FIELD, border_width=1, border_color=CARD_BORDER, text_color=TEXT,
            placeholder_text="Incolla il link di un brano, una playlist o un album…",
            placeholder_text_color=MUTED, font=self._font(14))
        self.url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.url_entry.bind("<Return>", lambda _e: self._avvia())
        self._bottone_secondario(riga_url, "Incolla", self._incolla).grid(row=0, column=1)

        riga_badge = ctk.CTkFrame(card, fg_color="transparent", height=26)
        riga_badge.grid(row=2, column=0, sticky="ew", padx=ip, pady=(8, 0))
        self.badge = ctk.CTkLabel(riga_badge, text="", corner_radius=8, height=24,
                                  font=self._font(12, "bold"), text_color="#FFFFFF")
        self.badge_hint = ctk.CTkLabel(riga_badge, text="", font=self._font(12),
                                       text_color=MUTED, height=24, anchor="w")
        self.badge_hint.pack(side="left")
        self._aggiorna_badge()

        opzioni = ctk.CTkFrame(card, fg_color="transparent")
        opzioni.grid(row=3, column=0, sticky="ew", padx=ip, pady=(16, 0))
        opzioni.grid_columnconfigure(0, weight=1)
        self._sezione(opzioni, "QUALITÀ MP3 (kbps)").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.bitrate_seg = ctk.CTkSegmentedButton(
            opzioni, values=BITRATES, height=38, corner_radius=12, font=self._font(13, "bold"),
            fg_color=FIELD, unselected_color=FIELD, unselected_hover_color=FIELD_HOVER,
            selected_color=ACCENT, selected_hover_color=ACCENT_HOVER, text_color=TEXT,
            command=lambda _v: self._salva_settings())
        self.bitrate_seg.grid(row=1, column=0, sticky="ew")
        bitrate_salvato = str(self.settings.get("bitrate", "320"))
        self.bitrate_seg.set(bitrate_salvato if bitrate_salvato in BITRATES else "320")

        self._sezione(opzioni, "EXTRA").grid(row=0, column=1, sticky="w", padx=(22, 0), pady=(0, 6))
        self.metadati_cb = ctk.CTkCheckBox(
            opzioni, text="Titolo, artista\ne copertina", variable=self.metadati_var,
            onvalue=True, offvalue=False, checkbox_width=22, checkbox_height=22, corner_radius=7,
            border_width=2, border_color=("#C9C3DD", "#4A4760"), fg_color=ACCENT,
            hover_color=ACCENT_HOVER, checkmark_color="#FFFFFF", text_color=TEXT,
            font=self._font(13), command=self._salva_settings)
        self.metadati_cb.grid(row=1, column=1, sticky="w", padx=(22, 0))

        self._sezione(card, "SALVA IN").grid(row=4, column=0, sticky="w", padx=ip, pady=(16, 6))
        riga_dir = ctk.CTkFrame(card, fg_color="transparent")
        riga_dir.grid(row=5, column=0, sticky="ew", padx=ip, pady=(0, 20))
        riga_dir.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(riga_dir, textvariable=self.dir_var, height=40, corner_radius=12,
                     fg_color=FIELD, border_width=1, border_color=CARD_BORDER, text_color=TEXT,
                     font=self._font(13)).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._bottone_secondario(riga_dir, "Sfoglia", self._scegli_cartella, height=40).grid(row=0, column=1, padx=(0, 8))
        self._bottone_secondario(riga_dir, "Apri", self._apri_cartella, width=64, height=40).grid(row=0, column=2)

        # --- Pulsante principale
        self.scarica_btn = ctk.CTkButton(
            self, text="↓   Scarica MP3", height=54, corner_radius=16, font=self._font(16, "bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#FFFFFF", command=self._avvia)
        self.scarica_btn.grid(row=2, column=0, sticky="ew", padx=px, pady=16)

        # --- Stato
        stato = self._card(self)
        stato.grid(row=3, column=0, sticky="ew", padx=px)
        stato.grid_columnconfigure(0, weight=1)
        self.stato_titolo = ctk.CTkLabel(stato, text="Pronto", font=self._font(15, "bold"),
                                         text_color=TEXT, anchor="w", height=22)
        self.stato_titolo.grid(row=0, column=0, sticky="ew", padx=(20, 8), pady=(16, 0))
        self.stato_pct = ctk.CTkLabel(stato, text="", font=self._font(15, "bold"),
                                      text_color=ACCENT, anchor="e", height=22)
        self.stato_pct.grid(row=0, column=1, sticky="e", padx=(0, 20), pady=(16, 0))
        self.stato_dettaglio = ctk.CTkLabel(
            stato, text="Incolla un link di YouTube o SoundCloud e premi Scarica.",
            font=self._font(13), text_color=MUTED, anchor="w", justify="left", height=20,
            wraplength=540)
        self.stato_dettaglio.grid(row=1, column=0, columnspan=2, sticky="ew", padx=20, pady=(2, 10))
        self.barra = ctk.CTkProgressBar(stato, height=8, corner_radius=4,
                                        fg_color=FIELD, progress_color=ACCENT)
        self.barra.grid(row=2, column=0, columnspan=2, sticky="ew", padx=20, pady=(0, 18))
        self._barra_valore(0)
        stato.bind("<Configure>", lambda e: self.stato_dettaglio.configure(
            wraplength=max(200, e.width - 60)))

        # --- Cronologia
        testa = ctk.CTkFrame(self, fg_color="transparent")
        testa.grid(row=4, column=0, sticky="ew", padx=px + 2, pady=(18, 6))
        testa.grid_columnconfigure(0, weight=1)
        self._sezione(testa, "SCARICATI DI RECENTE").grid(row=0, column=0, sticky="w")
        self.svuota_btn = ctk.CTkButton(testa, text="Svuota", width=60, height=22, fg_color="transparent",
                                        hover_color=FIELD_HOVER, text_color=MUTED,
                                        font=self._font(12), command=self._svuota_cronologia)
        self.svuota_btn.grid(row=0, column=1, sticky="e")

        self.lista = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0,
                                            scrollbar_button_color=CARD_BORDER,
                                            scrollbar_button_hover_color=MUTED)
        self.lista.grid(row=5, column=0, sticky="nsew", padx=(px - 6, px - 10), pady=(0, 18))
        self.lista.grid_columnconfigure(0, weight=1)
        self.vuoto = ctk.CTkLabel(self.lista, text="I brani scaricati appariranno qui.",
                                  font=self._font(13), text_color=MUTED)
        self.righe = []

    # ------------------------------------------------------------ interazioni
    def _aggiorna_badge(self):
        url = self.url_var.get().strip()
        piattaforma = _get_platform(url) if url else None
        if piattaforma in PIATTAFORME:
            nome, colore = PIATTAFORME[piattaforma]
            self.badge.configure(text=f"  ● {nome}  ", fg_color=colore)
            self.badge.pack(side="left", padx=(0, 10), before=self.badge_hint)
            self.badge_hint.configure(text="Link riconosciuto", text_color=MUTED)
        else:
            self.badge.pack_forget()
            if url:
                self.badge_hint.configure(text="Link non supportato: usa YouTube o SoundCloud",
                                          text_color=ERROR)
            else:
                self.badge_hint.configure(text="Funziona con brani singoli, playlist e album",
                                          text_color=MUTED)

    def _incolla(self):
        try:
            testo = self.clipboard_get().strip()
        except TclError:
            testo = ""
        if testo:
            self.url_var.set(testo)
            self.url_entry.icursor("end")
        self.url_entry.focus_set()

    def _autoincolla(self, _event=None):
        # Se negli appunti c'è un link supportato e il campo è vuoto, lo propone subito
        # (una sola volta per link, così se l'utente lo cancella non ricompare).
        if self.url_var.get().strip() or self._in_corso():
            return
        try:
            testo = self.clipboard_get().strip()
        except TclError:
            return
        if testo not in self._link_gia_visti and _get_platform(testo) != "unknown" and len(testo) < 500:
            self._link_gia_visti.add(testo)
            self.url_var.set(testo)

    def _scegli_cartella(self):
        d = filedialog.askdirectory(initialdir=self.dir_var.get() or str(Path.home()), parent=self)
        if d:
            self.dir_var.set(str(Path(d)))
            self._salva_settings()

    def _apri_cartella(self):
        cartella = Path(self.dir_var.get()).expanduser()
        cartella.mkdir(parents=True, exist_ok=True)
        apri(cartella)

    def _cambia_tema(self):
        nuovo = "light" if ctk.get_appearance_mode() == "Dark" else "dark"
        ctk.set_appearance_mode(nuovo)
        self.settings["tema"] = nuovo
        self._aggiorna_icona_tema()
        self._salva_settings()

    def _aggiorna_icona_tema(self):
        self.tema_btn.configure(text="☀" if ctk.get_appearance_mode() == "Dark" else "☾")

    # ---------------------------------------------------------------- download
    def _in_corso(self):
        return self.worker is not None and self.worker.is_alive()

    def _avvia(self):
        if self._in_corso():
            return
        url = self.url_var.get().strip()
        if not url:
            self._mostra_stato("Manca il link", "Incolla prima un link di YouTube o SoundCloud.", ERROR)
            self.url_entry.focus_set()
            return
        if _get_platform(url) == "unknown":
            self._mostra_stato("Link non supportato", "Per ora funzionano solo YouTube e SoundCloud.", ERROR)
            return

        self.annulla.clear()
        self._ultimo_tmp = None
        self._link_gia_visti.add(url)  # non riproporlo dagli appunti dopo il download
        self._salva_settings()
        self.scarica_btn.configure(text="×   Annulla", fg_color=DANGER, hover_color=DANGER_HOVER,
                                   command=self._annulla)
        self._mostra_stato("Analisi del link…", "Recupero le informazioni sul brano.", TEXT)
        self._barra_indeterminata(True)

        args = (url, self.dir_var.get().strip() or _cartella_musica_default(),
                int(self.bitrate_seg.get()), bool(self.metadati_var.get()))
        self.worker = threading.Thread(target=self._lavoro, args=args, daemon=True)
        self.worker.start()

    def _annulla(self):
        if self._in_corso():
            self.annulla.set()
            self.scarica_btn.configure(state="disabled", text="Annullamento…")

    def _lavoro(self, url, cartella, bitrate, metadati):
        """Gira in un thread separato: comunica con la UI solo tramite self.coda."""
        try:
            risultato = scarica_mp3(url, directory=cartella, bitrate=bitrate, metadati=metadati,
                                    progress_hook=self._hook_download,
                                    postprocessor_hook=self._hook_conversione,
                                    logger=_LoggerSilenzioso())
            percorsi = risultato if isinstance(risultato, list) else [risultato]
            self.coda.put(("fatto", percorsi))
        except yt_dlp.utils.DownloadCancelled:
            self._rimuovi_parziale()
            self.coda.put(("annullato", None))
        except Exception as e:
            self.coda.put(("errore", _pulisci_errore(e)))

    def _info_brano(self, info):
        info = info or {}
        return {
            "titolo": info.get("title") or "",
            "indice": info.get("playlist_index") or info.get("playlist_autonumber"),
            "totale": info.get("n_entries") or info.get("playlist_count"),
        }

    def _hook_download(self, d):
        if self.annulla.is_set():
            raise Annullato()
        brano = self._info_brano(d.get("info_dict"))
        if d.get("status") == "downloading":
            self._ultimo_tmp = d.get("tmpfilename")
            totale = d.get("total_bytes") or d.get("total_bytes_estimate")
            fatto = d.get("downloaded_bytes") or 0
            frazione = fatto / totale if totale else None
            if frazione is None and d.get("fragment_count"):
                frazione = (d.get("fragment_index") or 0) / d["fragment_count"]
            self.coda.put(("download", {**brano, "frazione": frazione, "byte": fatto, "totale_byte": totale,
                                        "velocita": d.get("speed"), "eta": d.get("eta")}))
        elif d.get("status") == "finished":
            self.coda.put(("download", {**brano, "frazione": 1.0, "byte": None, "totale_byte": None,
                                        "velocita": None, "eta": None}))

    def _hook_conversione(self, d):
        nome = d.get("postprocessor")
        # Niente annullamento qui: interrompere la conversione lascerebbe un MP3 a metà.
        if d.get("status") == "started":
            if nome in FASI_CONVERSIONE:
                self.coda.put(("fase", {**self._info_brano(d.get("info_dict")), "testo": FASI_CONVERSIONE[nome]}))
        elif d.get("status") == "finished" and nome == "MoveFiles":
            percorso = (d.get("info_dict") or {}).get("filepath")
            if percorso:
                self.coda.put(("brano_pronto", percorso))

    def _rimuovi_parziale(self):
        """Dopo un annullamento cancella il file .part e la copertina già scaricata."""
        if not self._ultimo_tmp:
            return
        tmp = Path(self._ultimo_tmp)                        # es. "Titolo.webm.part"
        media = tmp.with_suffix("") if tmp.suffix == ".part" else tmp
        base = str(media.with_suffix(""))                   # es. "Titolo"
        candidati = [tmp, Path(str(tmp) + ".ytdl")]
        candidati += [Path(base + ext) for ext in (".webp", ".jpg", ".jpeg", ".png")]
        for p in candidati:
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass

    def _leggi_coda(self):
        try:
            while True:
                tipo, dati = self.coda.get_nowait()
                getattr(self, f"_evento_{tipo}")(dati)
        except queue.Empty:
            pass
        self.after(100, self._leggi_coda)

    def _prefisso_playlist(self, dati):
        if dati.get("indice") and dati.get("totale") and dati["totale"] > 1:
            return f"Brano {dati['indice']} di {dati['totale']} · "
        return ""

    def _evento_download(self, dati):
        self._barra_indeterminata(False)
        frazione = dati["frazione"]
        self.stato_titolo.configure(text=_tronca(dati["titolo"] or "Download in corso", 60), text_color=TEXT)
        parti = []
        if dati["byte"] is not None and dati["totale_byte"]:
            parti.append(f"{_formatta_mb(dati['byte'])} di {_formatta_mb(dati['totale_byte'])}")
        if dati["velocita"]:
            parti.append(f"{_formatta_mb(dati['velocita'])}/s")
        if dati["eta"] is not None:
            parti.append(f"mancano {_formatta_eta(dati['eta'])}")
        dettaglio = " · ".join(parti) if parti else ("Download completato" if frazione == 1.0 else "Download…")
        self.stato_dettaglio.configure(text=self._prefisso_playlist(dati) + dettaglio, text_color=MUTED)
        if frazione is not None:
            self._barra_valore(frazione)
            self.stato_pct.configure(text=f"{int(frazione * 100)}%")

    def _evento_fase(self, dati):
        self._barra_indeterminata(True)
        self.stato_pct.configure(text="")
        if dati["titolo"]:
            self.stato_titolo.configure(text=_tronca(dati["titolo"], 60), text_color=TEXT)
        self.stato_dettaglio.configure(text=self._prefisso_playlist(dati) + dati["testo"], text_color=MUTED)

    def _evento_brano_pronto(self, percorso):
        self._aggiungi_alla_cronologia(percorso)

    def _evento_fatto(self, percorsi):
        for p in percorsi:
            self._aggiungi_alla_cronologia(p)
        self._fine_download()
        self._barra_valore(1)
        self.stato_pct.configure(text="")
        n = len(percorsi)
        dove = Path(percorsi[0]).parent.name or str(Path(percorsi[0]).parent)
        if n == 1:
            self._mostra_stato("✓  Fatto!", f"«{_tronca(Path(percorsi[0]).stem, 60)}» salvato in {dove}.", SUCCESS)
        else:
            self._mostra_stato("✓  Fatto!", f"{n} brani salvati in {dove}.", SUCCESS)
        self.url_var.set("")

    def _evento_annullato(self, _):
        self._fine_download()
        self._barra_valore(0)
        self.stato_pct.configure(text="")
        self._mostra_stato("Download annullato", "Nessun problema: puoi riprovare quando vuoi.", MUTED)

    def _evento_errore(self, messaggio):
        self._fine_download()
        self._barra_valore(0)
        self.stato_pct.configure(text="")
        self._mostra_stato("Qualcosa è andato storto", _tronca(messaggio, 300), ERROR)

    def _fine_download(self):
        self._barra_indeterminata(False)
        self.scarica_btn.configure(state="normal", text="↓   Scarica MP3", fg_color=ACCENT,
                                   hover_color=ACCENT_HOVER, command=self._avvia)

    def _mostra_stato(self, titolo, dettaglio, colore):
        self.stato_titolo.configure(text=titolo, text_color=colore)
        self.stato_dettaglio.configure(text=dettaglio, text_color=MUTED if colore != ERROR else ERROR)

    def _barra_valore(self, valore):
        # a 0 la barra di CTk disegna comunque un puntino: lo nascondiamo col colore di fondo
        self.barra.configure(progress_color=ACCENT if valore > 0 else FIELD)
        self.barra.set(valore)

    def _barra_indeterminata(self, attiva):
        if attiva and self.barra.cget("mode") != "indeterminate":
            self.barra.configure(mode="indeterminate", progress_color=ACCENT)
            self.barra.start()
        elif not attiva and self.barra.cget("mode") != "determinate":
            self.barra.stop()
            self.barra.configure(mode="determinate")
            self._barra_valore(0)

    # -------------------------------------------------------------- cronologia
    def _aggiungi_alla_cronologia(self, percorso, quando=None, salva=True):
        percorso = str(Path(percorso))
        if percorso in self._visti or not Path(percorso).exists():
            return
        self._visti.add(percorso)
        quando = quando or time.time()
        self.vuoto.grid_forget()

        riga = ctk.CTkFrame(self.lista, fg_color=CARD, corner_radius=14, border_width=1, border_color=CARD_BORDER)
        riga.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(riga, text="♪", width=38, height=38, corner_radius=19, fg_color=ACCENT_SOFT,
                     text_color=ACCENT, font=self._font(18, "bold")).grid(row=0, column=0, rowspan=2, padx=(12, 12), pady=10)
        p = Path(percorso)
        ctk.CTkLabel(riga, text=_tronca(p.stem, 46), font=self._font(13, "bold"), text_color=TEXT,
                     anchor="w", height=20).grid(row=0, column=1, sticky="sew", pady=(10, 0))
        try:
            dimensione = _formatta_mb(p.stat().st_size)
        except OSError:
            dimensione = ""
        orario = time.strftime("%d/%m %H:%M", time.localtime(quando))
        ctk.CTkLabel(riga, text=f"{dimensione} · {orario}", font=self._font(12), text_color=MUTED,
                     anchor="w", height=16).grid(row=1, column=1, sticky="new", pady=(0, 10))
        ctk.CTkButton(riga, text="▶", width=36, height=34, corner_radius=10, fg_color=ACCENT_SOFT,
                      hover_color=FIELD_HOVER, text_color=ACCENT, font=self._font(13, "bold"),
                      command=lambda: self._apri_file(percorso)).grid(row=0, column=2, rowspan=2, padx=(8, 6))
        ctk.CTkButton(riga, text="Mostra", width=70, height=34, corner_radius=10, fg_color=FIELD,
                      hover_color=FIELD_HOVER, text_color=TEXT, font=self._font(12, "bold"),
                      command=lambda: self._mostra_in_esplora(percorso)).grid(row=0, column=3, rowspan=2, padx=(0, 12))

        self.righe.insert(0, (percorso, quando, riga))
        for r in self.righe[MAX_CRONOLOGIA:]:
            r[2].destroy()
            self._visti.discard(r[0])
        self.righe = self.righe[:MAX_CRONOLOGIA]
        for i, (_, _, w) in enumerate(self.righe):
            w.grid(row=i, column=0, sticky="ew", padx=(6, 6), pady=(0, 8))
        if salva:
            self._salva_settings()

    def _carica_cronologia(self):
        for voce in reversed(self.settings.get("cronologia", [])):
            self._aggiungi_alla_cronologia(voce.get("percorso", ""), voce.get("quando"), salva=False)
        if not self.righe:
            self.vuoto.grid(row=0, column=0, pady=30)

    def _svuota_cronologia(self):
        for _, _, w in self.righe:
            w.destroy()
        self.righe.clear()
        self._visti.clear()
        self.vuoto.grid(row=0, column=0, pady=30)
        self._salva_settings()

    def _apri_file(self, percorso):
        if Path(percorso).exists():
            apri(percorso)
        else:
            self._mostra_stato("File non trovato", "Il file è stato spostato o eliminato.", ERROR)

    def _mostra_in_esplora(self, percorso):
        if Path(percorso).exists():
            mostra_nel_file_manager(percorso)
        else:
            self._apri_cartella()

    # ---------------------------------------------------------- impostazioni
    def _carica_settings(self):
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _salva_settings(self):
        self.settings.update({
            "cartella": self.dir_var.get(),
            "bitrate": self.bitrate_seg.get(),
            "metadati": bool(self.metadati_var.get()),
            "cronologia": [{"percorso": p, "quando": q} for p, q, _ in self.righe],
        })
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            SETTINGS_FILE.write_text(json.dumps(self.settings, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def report_callback_exception(self, exc, val, tb):
        # Con pythonw non c'è console: scrive l'errore su file e lo mostra nella finestra.
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with ERROR_LOG.open("a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + "".join(traceback.format_exception(exc, val, tb)) + "\n")
        except OSError:
            pass
        self._mostra_stato("Errore inatteso", f"{val} (dettagli in {ERROR_LOG})", ERROR)

    def _chiudi(self):
        self.annulla.set()
        self._salva_settings()
        self.destroy()


def _prepara_sistema():
    if WINDOWS:
        try:
            # Icona corretta nella barra delle applicazioni anche se avviato con pythonw.exe
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AudioDownloader.App")
        except Exception:
            pass
    elif MAC:
        try:
            # Nome giusto nella barra dei menu ("Audio Downloader" invece di "Python");
            # va fatto prima di creare la finestra. Richiede pyobjc (lo installa l'installer).
            from Foundation import NSBundle
            bundle = NSBundle.mainBundle()
            info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
            if info is not None:
                info["CFBundleName"] = APP_NAME
        except Exception:
            pass


def main():
    _prepara_sistema()
    AudioDownloaderApp().mainloop()


if __name__ == "__main__":
    main()
