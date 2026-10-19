#!/usr/bin/env python3
"""
Welke Instagram-accounts staan in Zernio, en op welke post deze starter.

    python3 engine/scripts/koppel.py                     toon de accounts in Zernio en welke in gebruik zijn
    python3 engine/scripts/koppel.py --link              een link om een Instagram-account aan Zernio te koppelen
    python3 engine/scripts/koppel.py --gebruik naam ...  post voortaan alleen op deze accounts (gebruikersnamen)
    python3 engine/scripts/koppel.py --erbij naam ...    zet deze accounts erbij; de accounts die er al stonden blijven
"""

import argparse
import json
import shutil
import sys

from instellingen import MIJN, vrije_naam
from zernio import Zernio, ZernioFout

ACCOUNTS = MIJN / "accounts.json"
PROFIELNAAM = "Trial Reels"


def in_gebruik():
    return json.loads(ACCOUNTS.read_text(encoding="utf-8")) if ACCOUNTS.exists() else []


def toon(z):
    eigen = {a["id"] for a in in_gebruik()}
    lijst = z.accounts()
    if not lijst:
        print("Er staat nog geen Instagram-account in Zernio. Maak een koppellink met: koppel.py --link")
        return
    for a in lijst:
        volgers = "onbekend" if a["volgers"] is None else int(a["volgers"])
        soort = ("trial reels" if a["volgers"] is not None and a["volgers"] >= 200
                 else "gewone reels (minder dan 200 volgers)" if a["volgers"] is not None else "nog niet te zeggen")
        print(f"@{a['gebruikersnaam']}: {volgers} volgers, {soort}"
              f"{', IN GEBRUIK' if a['id'] in eigen else ''}{'' if a['gezond'] else ', KOPPELING VERNIEUWEN in Zernio'}")


def link(z):
    profielen = z.profielen()
    profiel = next((p for p in profielen if p.get("name") == PROFIELNAAM), None) or (profielen[0] if profielen else None)
    profiel_id = profiel["_id"] if profiel else z.maak_profiel(PROFIELNAAM)
    print("Open deze link en log in met het Instagram-account dat je wilt koppelen.")
    print("Let op: Instagram koppelt het account waarmee je op dat moment ingelogd bent. Wissel in Instagram eerst naar het goede account.")
    print(z.koppellink(profiel_id))


def gebruik(z, namen, erbij=False):
    alle = {a["gebruikersnaam"].lower(): a for a in z.accounts()}
    if erbij:
        namen = [a["gebruikersnaam"] for a in in_gebruik()] + [n for n in namen if n.lstrip("@").lower() not in
                                                               {a["gebruikersnaam"].lower() for a in in_gebruik()}]
    kies, mist = [], []
    for n in namen:
        a = alle.get(n.lstrip("@").lower())
        (kies if a else mist).append(a or n)
    if mist:
        sys.exit(f"Niet gevonden in Zernio: {', '.join(mist)}. Koppel ze eerst (koppel.py --link) of kijk de naam na.")
    MIJN.mkdir(parents=True, exist_ok=True)
    if ACCOUNTS.exists():
        shutil.copy2(ACCOUNTS, vrije_naam(MIJN / "oud", "accounts", ".json"))
    ACCOUNTS.write_text(json.dumps([{"id": a["id"], "gebruikersnaam": a["gebruikersnaam"]} for a in kies],
                                   indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("In gebruik: " + ", ".join("@" + a["gebruikersnaam"] for a in kies))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--link", action="store_true")
    ap.add_argument("--gebruik", nargs="+", metavar="NAAM")
    ap.add_argument("--erbij", nargs="+", metavar="NAAM")
    a = ap.parse_args()
    try:
        z = Zernio()
        if a.link:
            link(z)
        elif a.gebruik or a.erbij:
            gebruik(z, a.gebruik or a.erbij, erbij=bool(a.erbij))
        else:
            toon(z)
    except ZernioFout as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
