#!/usr/bin/env python3
"""
De instellingen van de gebruiker: hoe de tekst in beeld eruitziet, hoe vaak er
gepost wordt en wanneer een reel een winner is.

De standaard staat in templates/config-standaard.json, de eigen keuzes in
mijn-trial-reels/config.json. De AI Suite maakt die keuzes met dezelfde regels
als hieronder (lib/trialstijl.js in de suite); wat hier niet door de keuring
komt, wordt niet gebruikt.

    python3 engine/scripts/instellingen.py                  toon de instellingen in gewone woorden
    python3 engine/scripts/instellingen.py --schrijf FILE   keur FILE (of - voor stdin) en bewaar hem
    python3 engine/scripts/instellingen.py --lettertypes    de lettertypes waaruit je kiest, met hun bestandsnaam
"""

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
FONTMAP = REPO / "engine" / "fonts"
STANDAARD = REPO / "templates" / "config-standaard.json"
MIJN = Path(os.environ.get("TRS_MIJN") or REPO / "mijn-trial-reels")   # TRS_MIJN alleen voor de tests
CONFIG = MIJN / "config.json"

# Dezelfde lettertypes als in de AI Suite, met de naam zoals de suite hem toont
FONTS = {
    "Poppins-ExtraBold.ttf": "Poppins ExtraBold",
    "Poppins-Bold.ttf": "Poppins Bold",
    "Montserrat-ExtraBold.ttf": "Montserrat ExtraBold",
    "Montserrat-Black.ttf": "Montserrat Black",
    "Inter-ExtraBold.ttf": "Inter ExtraBold",
    "Anton-Regular.ttf": "Anton",
    "BebasNeue-Regular.ttf": "Bebas Neue",
    "Oswald-Bold.ttf": "Oswald Bold",
    "BarlowCondensed-ExtraBold.ttf": "Barlow Condensed ExtraBold",
    "ArchivoBlack-Regular.ttf": "Archivo Black",
    "DMSerifDisplay.ttf": "DM Serif Display",
    "Playfair-Bold.ttf": "Playfair Display Bold",
    "PermanentMarker.ttf": "Permanent Marker",
    "Caveat-Bold.ttf": "Caveat Bold",
    "SpaceMono-Bold.ttf": "Space Mono Bold",
}
# Lettergrootte in pixels op een beeld van 1080 breed. Losse letters met een rand moeten groter zijn
# dan tekst op een blokje om even goed te lezen.
GROOTTES = {"blokje": {"klein": 52, "normaal": 60, "groot": 70}, "rand": {"klein": 72, "normaal": 84, "groot": 96}}


ZONE_RE = re.compile(r"^(Africa|America|Antarctica|Asia|Atlantic|Australia|Europe|Indian|Pacific)/[A-Za-z0-9_+\-/]+$")


class InstellingFout(Exception):
    pass


def _fout(wat):
    raise InstellingFout(f"Deze instelling klopt niet: {wat}")


def _kleur(v, wat):
    if isinstance(v, str) and len(v) == 7 and v[0] == "#" and all(c in "0123456789abcdefABCDEF" for c in v[1:]):
        return v.upper()
    _fout(f"{wat} is geen kleur zoals #FFFFFF")


def _keuze(v, lijst, wat):
    if v in lijst:
        return v
    _fout(f"{wat} moet een van deze zijn: {', '.join(lijst)}")


def _getal(v, laag, hoog, wat):
    # bool is in Python ook een int; die telt hier niet als getal
    if isinstance(v, int) and not isinstance(v, bool) and laag <= v <= hoog:
        return v
    _fout(f"{wat} moet een heel getal van {laag} tot en met {hoog} zijn")


def _aan_uit(v, wat):
    if isinstance(v, bool):
        return v
    _fout(f"{wat} moet aan (true) of uit (false) zijn")


def keur(cfg):
    """Geeft de instellingen in vaste vorm terug, of gooit InstellingFout met de reden."""
    if not isinstance(cfg, dict):
        _fout("het bestand is geen blok met instellingen")
    t, p, w = cfg.get("tekst"), cfg.get("posten"), cfg.get("winners")
    if not isinstance(t, dict) or not isinstance(p, dict) or not isinstance(w, dict):
        _fout("tekst, posten of winners ontbreekt")
    tijdzone = p.get("tijdzone")
    try:
        # Alleen echte plaatsen (Europe/Amsterdam); oude namen als US/Pacific of Etc/Unknown niet, net als in de AI Suite
        if not isinstance(tijdzone, str) or not ZONE_RE.match(tijdzone):
            raise ValueError
        ZoneInfo(tijdzone)
    except Exception:
        _fout("de tijdzone is onbekend (bijvoorbeeld Europe/Amsterdam)")
    uit = {
        "versie": 1,
        "tekst": {
            "font": _keuze(t.get("font"), list(FONTS), "het lettertype"),
            "vorm": _keuze(t.get("vorm"), ["blokje", "rand"], "de vorm van de tekst"),
            "kleur_tekst": _kleur(t.get("kleur_tekst"), "de tekstkleur"),
            "kleur_vlak": _kleur(t.get("kleur_vlak"), "de kleur van het blokje of de rand"),
            "grootte": _keuze(t.get("grootte"), ["klein", "normaal", "groot"], "de grootte"),
            "positie": _keuze(t.get("positie"), ["boven", "midden", "onder"], "de plek in beeld"),
            "hoofdletters": _aan_uit(t.get("hoofdletters"), "hoofdletters"),
        },
        "posten": {
            "per_dag": _getal(p.get("per_dag"), 1, 20, "het aantal posts per dag per account"),
            "minuten_tussen": _getal(p.get("minuten_tussen"), 30, 240, "het aantal minuten tussen twee posts"),
            "van": _getal(p.get("van"), 0, 23, "het eerste uur"),
            "tot": _getal(p.get("tot"), 1, 24, "het laatste uur"),
            "tijdzone": tijdzone,
            "doorzetten": _keuze(p.get("doorzetten"), ["zelf", "automatisch"], "doorzetten naar volgers"),
        },
        "winners": {
            "factor": _getal(w.get("factor"), 2, 10, "de factor voor een winner"),
            "min_views": _getal(w.get("min_views"), 0, 1000000, "het minimum aantal views"),
        },
    }
    po = uit["posten"]
    if po["tot"] <= po["van"]:
        _fout("het laatste uur moet na het eerste uur liggen")
    if (po["tot"] - po["van"]) * 60 < po["minuten_tussen"]:
        _fout("tussen het eerste en het laatste uur past niet eens één keer de tijd tussen twee posts")
    return uit


def vrije_naam(map_, stam, ext):
    """Een pad in map_ dat nog niet bestaat: stam-datum-tijd, en zo nodig -2, -3 erachter. Zo overschrijft niets ooit iets."""
    map_ = Path(map_)
    map_.mkdir(parents=True, exist_ok=True)
    tijd = datetime.now().strftime("%Y%m%d-%H%M%S")
    pad, n = map_ / f"{stam}-{tijd}{ext}", 2
    while pad.exists():
        pad, n = map_ / f"{stam}-{tijd}-{n}{ext}", n + 1
    return pad


def _samen(basis, eigen):
    """Per veld samenvoegen: wat de gebruiker zelf koos gaat voor, de rest komt uit de standaard."""
    uit = dict(basis)
    for k, v in (eigen or {}).items():
        uit[k] = _samen(basis[k], v) if isinstance(v, dict) and isinstance(basis.get(k), dict) else v
    return uit


def laad(pad=CONFIG):
    basis = json.loads(STANDAARD.read_text(encoding="utf-8"))
    eigen = json.loads(Path(pad).read_text(encoding="utf-8")) if Path(pad).exists() else {}
    return keur(_samen(basis, eigen))


def _meng(oud, nieuw):
    """Twee eigen keuzes samen, per veld: wat nieuw is gaat voor."""
    uit = dict(oud or {})
    for k, v in (nieuw or {}).items():
        uit[k] = _meng(uit.get(k), v) if isinstance(v, dict) and isinstance(uit.get(k), dict) else v
    return uit


# Pas als al deze velden zelf gekozen zijn, telt een blok als gekozen (de setup kijkt daarnaar)
NODIG = {"posten": ("per_dag", "minuten_tussen", "van", "tot", "tijdzone", "doorzetten"), "winners": ("factor", "min_views")}


def lees_eigen(pad=CONFIG):
    """Wat de gebruiker zelf koos, zonder de standaard, plus de velden die niet (meer) door de keuring komen. Een
    ongeldig veld valt weg; de rest van de eigen keuzes blijft (de vorige versie blijft bewaard in oud/)."""
    pad = Path(pad)
    try:
        eigen = json.loads(pad.read_text(encoding="utf-8")) if pad.exists() else {}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}, ["het hele bestand"]
    if not isinstance(eigen, dict):
        return {}, ["het hele bestand"]
    standaard = json.loads(STANDAARD.read_text(encoding="utf-8"))

    def past(keuzes):
        try:
            keur(_samen(standaard, keuzes))
            return True
        except (InstellingFout, AttributeError, TypeError):
            return False

    goed, weg = {}, []
    for blok in ("tekst", "posten", "winners"):
        waarden = eigen.get(blok)
        if waarden is None:
            continue
        if not isinstance(waarden, dict):
            weg.append(blok)
        elif past({**goed, blok: waarden}):
            goed[blok] = dict(waarden)
        else:
            # Eerst: is er één veld dat alles laat vallen? Dan alleen dat weg (van en tot kloppen soms alleen samen)
            een = next((k for k in waarden if past({**goed, blok: {x: v for x, v in waarden.items() if x != k}})), None)
            if een is not None:
                goed[blok] = {x: v for x, v in waarden.items() if x != een}
                weg.append(f"{blok}.{een}")
                continue
            goed[blok] = {}
            for k, v in waarden.items():
                if past({**goed, blok: {**goed[blok], k: v}}):
                    goed[blok][k] = v
                else:
                    weg.append(f"{blok}.{k}")
    return goed, weg


def eigen_keuzes(pad=CONFIG):
    """Wat de gebruiker zelf koos, zonder de standaard."""
    return lees_eigen(pad)[0]


def nog_niet_gekozen(pad=CONFIG):
    """Welke blokken de gebruiker nog niet helemaal zelf koos, in gewone woorden."""
    eigen = eigen_keuzes(pad)
    return [w for blok, w in (("posten", "de postregels"), ("winners", "wanneer iets een winner is"))
            if not all(k in (eigen.get(blok) or {}) for k in NODIG[blok])]


def schrijf(nieuw, pad=CONFIG):
    """Keurt de nieuwe keuzes en bewaart ze. Alleen wat de gebruiker zelf koos komt in het bestand (de standaard vult de
    rest aan bij het laden), zodat te zien is wat nog niet gevraagd is. De vorige versie gaat naar mijn-trial-reels/oud/."""
    pad = Path(pad)
    if not isinstance(nieuw, dict):
        _fout("het bestand is geen blok met instellingen")
    eigen = _meng(eigen_keuzes(pad), {k: v for k, v in nieuw.items() if k in ("tekst", "posten", "winners")})
    cfg = keur(_samen(json.loads(STANDAARD.read_text(encoding="utf-8")), eigen))
    bewaar = {"versie": 1, **{blok: {k: cfg[blok][k] for k in eigen[blok] if k in cfg[blok]}
                              for blok in ("tekst", "posten", "winners") if isinstance(eigen.get(blok), dict)}}
    pad.parent.mkdir(parents=True, exist_ok=True)
    if pad.exists():
        shutil.copy2(pad, vrije_naam(pad.parent / "oud", "config", ".json"))
    pad.write_text(json.dumps(bewaar, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return cfg


def font_pad(cfg):
    return FONTMAP / cfg["tekst"]["font"]


def per_dag_echt(p):
    """Hoeveel er per dag echt passen: het venster gedeeld door de minuten ertussen kan minder zijn dan per_dag."""
    return max(1, min(p["per_dag"], (p["tot"] - p["van"]) * 60 // p["minuten_tussen"]))


def in_woorden(cfg):
    t, p, w = cfg["tekst"], cfg["posten"], cfg["winners"]
    past = per_dag_echt(p)
    vorm = (f"tekst {t['kleur_tekst']} op een blokje in {t['kleur_vlak']}" if t["vorm"] == "blokje"
            else f"tekst {t['kleur_tekst']} met een rand in {t['kleur_vlak']}")
    return "\n".join([
        f"Tekst in beeld: {FONTS[t['font']]}, {vorm}, {t['grootte']}, {t['positie']} in beeld"
        f"{', in hoofdletters' if t['hoofdletters'] else ''}.",
        f"Posten: hooguit {p['per_dag']} per account per dag, minstens {p['minuten_tussen']} minuten ertussen, "
        f"tussen {p['van']}:00 en {p['tot']}:00 ({p['tijdzone']})"
        + (f"; in dat venster passen er {past} per dag." if past < p["per_dag"] else "."),
        "Doorzetten naar volgers: " + ("doe je zelf in de Instagram-app." if p["doorzetten"] == "zelf"
                                       else "Instagram doet het vanzelf als een trial reel goed loopt."),
        f"Winner: minstens {w['factor']} keer de gewone views van het account en minstens {w['min_views']} views.",
    ])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--schrijf", metavar="FILE", help="keur dit bestand (of - voor stdin) en bewaar het")
    ap.add_argument("--lettertypes", action="store_true", help="toon de lettertypes en hun bestandsnaam")
    a = ap.parse_args()
    if a.lettertypes:
        print("\n".join(f"{naam}: \"font\": \"{bestand}\"" for bestand, naam in FONTS.items()))
        return
    try:
        if a.schrijf:
            tekst = sys.stdin.read() if a.schrijf == "-" else Path(a.schrijf).read_text(encoding="utf-8")
            weg = lees_eigen()[1]
            cfg = schrijf(json.loads(tekst))
            print(f"Bewaard in {CONFIG}.")
            if weg:
                print(f"Niet meer geldig en weggelaten uit de eigen keuzes: {', '.join(weg)} (de vorige versie staat in {MIJN / 'oud'}).")
        else:
            cfg = laad()
        print(in_woorden(cfg))
        nog = nog_niet_gekozen()
        if nog:
            print(f"Nog niet (helemaal) gekozen: {' en '.join(nog)} (setup stap 5); tot dan gelden de standaardwaarden hierboven.")
    except json.JSONDecodeError as e:
        sys.exit(f"Dit is geen geldig blok met instellingen: {e}")
    except InstellingFout as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
