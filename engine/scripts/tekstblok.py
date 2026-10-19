#!/usr/bin/env python3
"""
De tekst in beeld als doorzichtige PNG van 1080 bij 1920, in de stijl uit de instellingen.

Twee vormen:
1. blokje: per regel een gevuld blokje met ronde hoeken, strak om de tekst, zoals
   de tekstfunctie in Instagram zelf. Regels van bijna gelijke breedte worden één
   blok, en de overgang tussen een brede en een smalle regel is een vloeiende bocht.
2. rand: losse letters met een rand eromheen.

Elk teken komt uit het gekozen lettertype. Heeft dat het niet, dan uit het emojifont
van de Mac, in kleur (zoals 👇 of ❤). Heeft geen van beide het, dan geeft het een
duidelijke fout in plaats van een leeg vierkantje of een teken dat stil wegvalt.
Emoji die uit meer stukken bestaan (vlaggen, een huidskleur, een gezin) kunnen niet:
die zou het hier in losse stukken zetten.
"""

import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from instellingen import GROOTTES, font_pad

CANVAS = (1080, 1920)
# De veilige zone van een reel (Meta, richtlijn voor Reels): bovenin 14 procent voor de balk van Instagram,
# onderin 35 procent voor naam, caption en geluid, en rechts de knoppen.
MAX_BREEDTE = 860             # breedste blok, met de marge erbinnen; laat de knoppen van Instagram rechts vrij
BOVEN_Y = 270                 # bovenkant van het blok bij "boven"
ONDER_Y = 1250                # onderkant van het blok bij "onder"
MIDDEN_Y = (BOVEN_Y + ONDER_Y) // 2   # midden van het blok bij "midden": het midden van de veilige zone
MAX_REGELS = 6

EMOJI_FONTS = ["/System/Library/Fonts/Apple Color Emoji.ttc"]
EMOJI_BITMAP = 160            # Apple Color Emoji heeft alleen vaste maten; 160 is de grootste
ONZICHTBAAR = "️"        # het teken dat zegt "als emoji tonen"; tekent zelf niets
SAMENGESTELD = re.compile("[‍\U0001F3FB-\U0001F3FF\U0001F1E6-\U0001F1FF]")


class TekstFout(Exception):
    pass


_cmaps = {}


def _cmap(pad):
    if pad not in _cmaps:
        from fontTools.ttLib import TTFont
        _cmaps[pad] = (TTFont(str(pad), fontNumber=0, lazy=True) if str(pad).endswith(".ttc") else TTFont(str(pad), lazy=True)).getBestCmap()
    return _cmaps[pad]


def _emoji_font():
    return next((pad for pad in EMOJI_FONTS if Path(pad).exists()), None)


def soort(teken, cmap_tekst):
    """tekst (uit het lettertype), emoji (uit het emojifont), stil (tekent niets) of mist."""
    if teken.isspace() or ord(teken) in cmap_tekst:
        return "tekst"
    if teken == ONZICHTBAAR:
        return "stil"
    emoji = _emoji_font()
    return "emoji" if emoji and ord(teken) in _cmap(emoji) else "mist"


def _stukken(regel, cmap_tekst):
    """Een regel in opeenvolgende stukken tekst en emoji."""
    uit = []
    for teken in regel:
        s = soort(teken, cmap_tekst)
        if s == "stil":
            continue
        s = "tekst" if s == "mist" else s
        if uit and uit[-1][0] == s:
            uit[-1] = (s, uit[-1][1] + teken)
        else:
            uit.append((s, teken))
    return uit


def ontbrekende_tekens(tekst, fontbestand):
    """De tekens die niet te tekenen zijn: niet in het lettertype en niet in het emojifont."""
    cmap = _cmap(fontbestand)
    return sorted({c for c in tekst if soort(c, cmap) == "mist"})


_emoji_cache = {}


def _emoji(teken, hoogte):
    sleutel = (teken, hoogte)
    if sleutel not in _emoji_cache:
        font = ImageFont.truetype(_emoji_font(), EMOJI_BITMAP)
        kaart = Image.new("RGBA", (EMOJI_BITMAP * 2, EMOJI_BITMAP * 2), (0, 0, 0, 0))
        ImageDraw.Draw(kaart).text((10, 10), teken, font=font, embedded_color=True)
        vak = kaart.getbbox()
        if vak:
            kaart = kaart.crop(vak)
            kaart = kaart.resize((max(1, round(kaart.width * hoogte / kaart.height)), hoogte), Image.LANCZOS)
        _emoji_cache[sleutel] = kaart if vak else None
    return _emoji_cache[sleutel]


class _Zetter:
    """Meet en tekent tekst met emoji ertussen, voor één lettertype en grootte."""

    def __init__(self, font, cmap, grootte, rand=0):
        self.f, self.cmap, self.g, self.rand = font, cmap, grootte, rand
        self.emoji_h = int(grootte * 0.95)

    def breedte(self, regel):
        b = 0.0
        for soort_, s in _stukken(regel, self.cmap):
            if soort_ == "tekst":
                b += self.f.getlength(s)
            else:
                for teken in s:
                    plaatje = _emoji(teken, self.emoji_h)
                    if plaatje:
                        b += plaatje.width + self.emoji_h * 0.16
        return b + 2 * self.rand

    def breek(self, tekst, max_b):
        regels = []
        for alinea in tekst.split("\n"):
            huidig = ""
            for woord in alinea.split():
                kandidaat = f"{huidig} {woord}".strip()
                if not huidig or self.breedte(kandidaat) <= max_b:
                    huidig = kandidaat
                else:
                    regels.append(huidig)
                    huidig = woord
            regels.append(huidig)
        return regels

    def inkt(self, regel):
        """Boven- en onderkant van de zichtbare inkt van een regel, vanaf de bovenkant van de regel."""
        asc = self.f.getmetrics()[0]
        boven, onder = [], []
        for soort_, s in _stukken(regel, self.cmap):
            if soort_ == "tekst" and s.strip():
                vak = self.f.getbbox(s.strip())
                boven.append(vak[1] - self.rand)
                onder.append(vak[3] + self.rand)
            elif soort_ == "emoji":
                boven.append(asc - self.emoji_h * 0.92)
                onder.append(asc + self.emoji_h * 0.08)
        return (min(boven), max(onder)) if boven else (0, asc)

    def teken(self, plaat, regel, x, y, kleur, randkleur=None):
        tekening = ImageDraw.Draw(plaat)
        x += self.rand
        basislijn = y + self.f.getmetrics()[0]
        for soort_, s in _stukken(regel, self.cmap):
            if soort_ == "tekst":
                if randkleur:
                    tekening.text((x, y), s, font=self.f, fill=kleur, stroke_width=self.rand, stroke_fill=randkleur)
                else:
                    tekening.text((x, y), s, font=self.f, fill=kleur)
                x += self.f.getlength(s)
            else:
                for teken in s:
                    plaatje = _emoji(teken, self.emoji_h)
                    if plaatje:
                        plaat.alpha_composite(plaatje, (int(x + self.emoji_h * 0.06), int(basislijn - self.emoji_h * 0.92)))
                        x += plaatje.width + self.emoji_h * 0.16


def _rgb(hexkleur):
    return tuple(int(hexkleur[i:i + 2], 16) for i in (1, 3, 5))


def _top(positie, hoogte):
    if positie == "boven":
        return BOVEN_Y
    if positie == "midden":
        return MIDDEN_Y - hoogte // 2
    return ONDER_Y - hoogte


# Altijd de eenvoudige opmaak, zonder kerning: zo meet en tekent elke Mac hetzelfde (met of zonder raqm in Pillow), en
# het voorbeeld in de AI Suite zet de kerning ook uit (font-kerning: none) zodat het op dezelfde plek afbreekt.
BASIS_OPMAAK = getattr(getattr(ImageFont, "Layout", None), "BASIC", getattr(ImageFont, "LAYOUT_BASIC", 0))


def _schik(tekst, t, fontbestand, cmap, g):
    """De regels en maten bij lettergrootte g, of TekstFout als het zo niet netjes in beeld past."""
    font = ImageFont.truetype(str(fontbestand), g, layout_engine=BASIS_OPMAAK)
    if t["vorm"] == "blokje":
        # Maten van het blokje als deel van de lettergrootte, zoals de tekstfunctie van Instagram
        z = _Zetter(font, cmap, g)
        pad_x, radius, vak_h, stap = int(g * 0.42), int(g * 0.20), int(g * 1.85), int(g * 1.26)
        regels = z.breek(tekst, MAX_BREEDTE - 2 * pad_x)
        hoogte = (len(regels) - 1) * stap + vak_h
    else:
        z = _Zetter(font, cmap, g, rand=max(2, round(g * 0.08)))
        pad_x, radius, vak_h, stap = 0, 0, 0, int(g * 1.2)
        regels = z.breek(tekst, MAX_BREEDTE)
        asc, desc = font.getmetrics()
        hoogte = (len(regels) - 1) * stap + asc + desc + 2 * z.rand
    if len(regels) > MAX_REGELS:
        raise TekstFout(f"De tekst wordt {len(regels)} regels; hooguit {MAX_REGELS} passen netjes. Maak hem korter of kies een kleinere letter.")
    breedtes = [z.breedte(r) + 2 * pad_x for r in regels]
    if max(breedtes) > MAX_BREEDTE:
        raise TekstFout("Eén woord is te breed: het zou over de knoppen van Instagram vallen. Maak het korter of kies een kleinere letter.")
    top = _top(t["positie"], hoogte)
    if top < BOVEN_Y or top + hoogte > ONDER_Y:
        raise TekstFout("De tekst past niet tussen de balken van Instagram. Maak hem korter, kies een kleinere letter of een andere plek.")
    return z, regels, breedtes, hoogte, pad_x, stap, vak_h, radius, g


def render(tekst, cfg):
    """De tekst als RGBA-plaatje op 1080 bij 1920. Gooit TekstFout als hij niet netjes in beeld past."""
    t = cfg["tekst"]
    tekst = (tekst or "").strip()
    if not tekst:
        raise TekstFout("De tekst in beeld is leeg.")
    if SAMENGESTELD.search(tekst):
        raise TekstFout("Vlaggen, emoji met een huidskleur en emoji die uit meer emoji bestaan kunnen niet in beeld. "
                        "Kies een eenvoudige emoji of zet hem in de caption.")
    if t["hoofdletters"]:
        tekst = tekst.upper()
    fontbestand = font_pad(cfg)
    mist = ontbrekende_tekens(tekst, fontbestand)
    if mist:
        raise TekstFout(f"Het lettertype {fontbestand.name} heeft deze tekens niet, en het emojifont ook niet: {' '.join(mist)}. "
                        "Haal ze weg of kies een ander lettertype.")
    cmap = _cmap(fontbestand)
    # Past de tekst niet, dan eerst een iets kleinere letter (tot 80 procent) voordat het een fout wordt: een lang
    # Nederlands woord als "Ondernemersvaardigheden" mag de klant niet steeds tegenhouden
    fout = None
    for schaal in (1.0, 0.9, 0.8):
        try:
            z, regels, breedtes, hoogte, pad_x, stap, vak_h, radius, g = _schik(tekst, t, fontbestand, cmap, round(GROOTTES[t["vorm"]][t["grootte"]] * schaal))
            break
        except TekstFout as e:
            fout = e
    else:
        raise fout
    top = _top(t["positie"], hoogte)
    plaat = Image.new("RGBA", CANVAS, (0, 0, 0, 0))

    kleur = _rgb(t["kleur_tekst"]) + (255,)
    vlak = _rgb(t["kleur_vlak"])
    if t["vorm"] == "rand":
        for i, r in enumerate(regels):
            x = (CANVAS[0] - z.breedte(r)) / 2
            z.teken(plaat, r, x, top + i * stap, kleur, randkleur=vlak + (255,))
        return plaat

    # Regels die bijna even breed zijn, krijgen precies dezelfde breedte en worden samen één blok
    groepen = []
    for i, b in enumerate(breedtes):
        if groepen and abs(groepen[-1][2] - b) < g * 0.5:
            a, _, oud = groepen[-1]
            groepen[-1] = (a, i, max(oud, b))
        else:
            groepen.append((i, i, b))
    extra = (vak_h - stap) // 2
    vakjes, groep_van = [], {}
    for gi, (a, b, vak_b) in enumerate(groepen):
        x0 = int((CANVAS[0] - vak_b) / 2)
        y0 = top if a == 0 else top + a * stap + extra
        y1 = top + b * stap + vak_h if b == len(regels) - 1 else top + (b + 1) * stap + extra
        vakjes.append((x0, y0, x0 + int(vak_b), y1))
        for i in range(a, b + 1):
            groep_van[i] = gi
    # De blokjes als één vorm; vervagen en weer scherp zetten maakt van elke naad een vloeiende bocht
    masker = Image.new("L", CANVAS, 0)
    for vak in vakjes:
        ImageDraw.Draw(masker).rounded_rectangle(vak, radius=radius, fill=255)
    if len(vakjes) > 1:
        masker = masker.filter(ImageFilter.GaussianBlur(radius * 0.55))
        masker = masker.point(lambda v: max(0, min(255, (v - 118) * 13)))
    plaat.paste(Image.new("RGBA", CANVAS, vlak + (255,)), (0, 0), masker)

    # De zichtbare inkt van alle regels samen staat precies in het midden van het blok
    inkt = [z.inkt(r) for r in regels]
    inkt_boven = min(i * stap + b[0] for i, b in enumerate(inkt))
    inkt_onder = max(i * stap + b[1] for i, b in enumerate(inkt))
    verschuif = int((hoogte - (inkt_onder - inkt_boven)) / 2 - inkt_boven)
    for i, r in enumerate(regels):
        x0, _, x1, _ = vakjes[groep_van[i]]
        z.teken(plaat, r, x0 + ((x1 - x0) - z.breedte(r)) / 2, top + i * stap + verschuif, kleur)
    return plaat


if __name__ == "__main__":
    import argparse
    from instellingen import laad
    ap = argparse.ArgumentParser(description="Teken de tekst in beeld als PNG, om te bekijken.")
    ap.add_argument("tekst")
    ap.add_argument("uit")
    a = ap.parse_args()
    achter = Image.new("RGBA", CANVAS, (70, 90, 110, 255))
    achter.alpha_composite(render(a.tekst.replace("\\n", "\n"), laad()))
    achter.convert("RGB").save(a.uit, quality=92)
    print("geschreven:", a.uit)
