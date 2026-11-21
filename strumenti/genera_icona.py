"""Disegna l'icona dell'app in app/assets/ (icon.png 1024 px e icon.ico per Windows).

Rispetto alla versione Mac il margine è sottile: le icone di Windows riempiono il riquadro.

Serve solo a chi sviluppa: le icone generate sono già nel repository.
    python strumenti/genera_icona.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parent.parent / "app" / "assets"
S = 1024
MARGINE = 36


def _testa(img, cx, cy):
    """Testa della nota: ellisse inclinata."""
    layer = Image.new("RGBA", (230, 160), (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse((0, 0, 229, 159), fill=(255, 255, 255, 255))
    layer = layer.rotate(22, resample=Image.BICUBIC, expand=True)
    img.alpha_composite(layer, (round(cx - layer.width / 2), round(cy - layer.height / 2)))


def genera_icona():
    ASSETS.mkdir(parents=True, exist_ok=True)
    # sfondo: gradiente diagonale viola -> fucsia dentro un quadrato arrotondato
    grad = Image.linear_gradient("L").resize((S * 2, S * 2)).rotate(45, resample=Image.BICUBIC)
    grad = grad.crop((S // 2, S // 2, S // 2 + S, S // 2 + S))
    sfondo = Image.composite(Image.new("RGBA", (S, S), "#EC4899"), Image.new("RGBA", (S, S), "#6D28D9"), grad)
    # margine sottile e angoli arrotondati
    forma = Image.new("L", (S, S), 0)
    ImageDraw.Draw(forma).rounded_rectangle((MARGINE, MARGINE, S - MARGINE, S - MARGINE), radius=200, fill=255)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(sfondo, (0, 0), forma)

    # leggera luce in alto
    luce = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(luce).ellipse((-200, -560, S + 200, 440), fill=(255, 255, 255, 34))
    img.alpha_composite(Image.composite(luce, Image.new("RGBA", (S, S), (0, 0, 0, 0)), forma))

    # doppia croma bianca, ridotta e centrata nella forma
    nota = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(nota)
    w = (255, 255, 255, 255)
    d.rectangle((402, 330, 460, 700), fill=w)
    d.rectangle((664, 270, 722, 640), fill=w)
    d.polygon([(402, 318), (722, 250), (722, 360), (402, 428)], fill=w)
    _testa(nota, 350, 712)
    _testa(nota, 612, 652)
    lato = int(S * 0.8 * (S - 2 * MARGINE) / (S - 200))  # stesse proporzioni della versione Mac
    nota = nota.resize((lato, lato), Image.LANCZOS)
    img.alpha_composite(nota, ((S - lato) // 2 + 6, (S - lato) // 2 + 6))

    img.save(ASSETS / "icon.png")
    img.resize((256, 256), Image.LANCZOS).save(
        ASSETS / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("Icone create in", ASSETS)


if __name__ == "__main__":
    genera_icona()
