"""Genera l'icona dell'app (assets/) e crea il collegamento "Audio Downloader" sul desktop.

Rilancialo se sposti la cartella del progetto o cambi ambiente Python:
    python crea_collegamento.py
"""
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

BASE = Path(__file__).resolve().parent
ASSETS = BASE / "assets"
NOME = "Audio Downloader"


def _nota(draw, s):
    """Doppia croma (♫) bianca, coordinate pensate per un canvas 1024 e scalate con s."""
    w = (255, 255, 255, 255)
    k = lambda *v: [round(x * s) for x in v]
    draw.rectangle(k(402, 330, 460, 700), fill=w)                             # gambo sinistro
    draw.rectangle(k(664, 270, 722, 640), fill=w)                             # gambo destro
    draw.polygon([tuple(k(402, 318)), tuple(k(722, 250)), tuple(k(722, 360)), tuple(k(402, 428))], fill=w)  # trave


def _testa(img, cx, cy, s):
    """Testa della nota: ellisse inclinata incollata sul canvas."""
    lw, lh = round(230 * s), round(160 * s)
    layer = Image.new("RGBA", (lw, lh), (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse((0, 0, lw - 1, lh - 1), fill=(255, 255, 255, 255))
    layer = layer.rotate(22, resample=Image.BICUBIC, expand=True)
    img.alpha_composite(layer, (round(cx * s - layer.width / 2), round(cy * s - layer.height / 2)))


def genera_icona():
    ASSETS.mkdir(exist_ok=True)
    S = 1024
    # sfondo: gradiente diagonale viola -> fucsia dentro un quadrato arrotondato
    mask_grad = Image.linear_gradient("L").resize((S * 2, S * 2)).rotate(45, resample=Image.BICUBIC)
    mask_grad = mask_grad.crop((S // 2, S // 2, S // 2 + S, S // 2 + S))
    sfondo = Image.composite(Image.new("RGBA", (S, S), "#EC4899"), Image.new("RGBA", (S, S), "#6D28D9"), mask_grad)
    forma = Image.new("L", (S, S), 0)
    ImageDraw.Draw(forma).rounded_rectangle((40, 40, S - 40, S - 40), radius=230, fill=255)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(sfondo, (0, 0), forma)

    # leggera luce in alto per dare profondità
    luce = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(luce).ellipse((-200, -620, S + 200, 430), fill=(255, 255, 255, 34))
    luce_mask = Image.new("L", (S, S), 0)
    luce_mask.paste(forma)
    img.alpha_composite(Image.composite(luce, Image.new("RGBA", (S, S), (0, 0, 0, 0)), luce_mask))

    _nota(ImageDraw.Draw(img), 1)
    _testa(img, 350, 712, 1)
    _testa(img, 612, 652, 1)

    img.resize((256, 256), Image.LANCZOS).save(ASSETS / "icon.png")
    img.resize((256, 256), Image.LANCZOS).save(
        ASSETS / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("Icona creata in", ASSETS)


def crea_collegamento():
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.exists():
        pythonw = Path(sys.executable)
    q = lambda p: str(p).replace("'", "''")  # stringa sicura per PowerShell tra apici singoli
    script = f"""
$desktop = [Environment]::GetFolderPath('Desktop')
$lnk = Join-Path $desktop '{NOME}.lnk'
$s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
$s.TargetPath = '{q(pythonw)}'
$s.Arguments = '"{q(BASE / "gui.py")}"'
$s.WorkingDirectory = '{q(BASE)}'
$s.IconLocation = '{q(ASSETS / "icon.ico")},0'
$s.Description = 'Scarica MP3 da YouTube e SoundCloud'
$s.Save()
Write-Output $lnk
"""
    out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit("Errore nella creazione del collegamento:\n" + out.stderr)
    print("Collegamento creato:", out.stdout.strip())


if __name__ == "__main__":
    genera_icona()
    crea_collegamento()
