#!/usr/bin/env python3
"""
Welke Instagram-accounts staan in de koppeling (Zernio of Metricool), en op welke post deze starter.

    python3 engine/scripts/koppel.py                     toon de accounts en welke in gebruik zijn
    python3 engine/scripts/koppel.py --link              Zernio: een link om een Instagram-account te koppelen
                                                         (bij Metricool koppel je Instagram in Metricool zelf)
    python3 engine/scripts/koppel.py --gebruik naam ...  post voortaan alleen op deze accounts (gebruikersnaam, of bij
                                                         Metricool het nummer van het merk als een naam twee keer voorkomt)
    python3 engine/scripts/koppel.py --erbij naam ...    zet deze accounts erbij; de accounts die er al stonden blijven
"""

import argparse
import json
import shutil
import sys

from instellingen import MIJN, InstellingFout, laad, vrije_naam
from koppelfout import KoppelFout
from koppeling import maak as maak_koppeling

ACCOUNTS = MIJN / "accounts.json"
PROFIELNAAM = "Trial Reels"


def in_gebruik():
    return json.loads(ACCOUNTS.read_text(encoding="utf-8")) if ACCOUNTS.exists() else []


def toon(z):
    eigen = {a["id"] for a in in_gebruik()}
    lijst = z.accounts()
    if not lijst:
        print(f"Er staat nog geen Instagram-account in {z.naam}. "
              + ("Maak een koppellink met: koppel.py --link" if z.naam == "Zernio"
                 else "Maak in Metricool een merk met het Instagram-account erin, en kijk dan opnieuw."))
        return
    for a in lijst:
        volgers = "onbekend" if a["volgers"] is None else int(a["volgers"])
        soort = ("trial reels" if a["volgers"] is not None and a["volgers"] >= 200
                 else "gewone reels (minder dan 200 volgers)" if a["volgers"] is not None else "nog niet te zeggen")
        print(f"@{a['gebruikersnaam']}: {volgers} volgers, {soort}"
              f"{' (merk ' + str(a.get('profiel') or '?') + ', nummer ' + a['id'] + ')' if z.naam == 'Metricool' else ''}"
              f"{', IN GEBRUIK' if a['id'] in eigen else ''}{'' if a['gezond'] else ', KOPPELING VERNIEUWEN in ' + z.naam}")


def link(z):
    if z.naam != "Zernio":
        print("Bij Metricool koppel je Instagram in Metricool zelf: maak daar een merk (of open een bestaand merk) en koppel "
              "het Instagram-account eraan. Daarna toont koppel.py het account en zet je het in gebruik met --gebruik.")
        return
    profielen = z.profielen()
    profiel = next((p for p in profielen if p.get("name") == PROFIELNAAM), None) or (profielen[0] if profielen else None)
    profiel_id = profiel["_id"] if profiel else z.maak_profiel(PROFIELNAAM)
    print("Open deze link en log in met het Instagram-account dat je wilt koppelen.")
    print("Let op: Instagram koppelt het account waarmee je op dat moment ingelogd bent. Wissel in Instagram eerst naar het goede account.")
    print(z.koppellink(profiel_id))


def gebruik(z, namen, erbij=False):
    lijst = z.accounts()

    def vind(n):
        n = str(n).lstrip("@")
        return [a for a in lijst if a["id"] == n] or [a for a in lijst if a["gebruikersnaam"].lower() == n.lower()]

    if erbij:
        namen = [a["id"] if vind(a["id"]) else a["gebruikersnaam"] for a in in_gebruik()] + list(namen)
    kies, mist, dubbel = [], [], []
    for n in namen:
        gevonden = vind(n)
        if not gevonden:
            mist.append(n)
        elif len(gevonden) > 1:
            dubbel.append(f"@{gevonden[0]['gebruikersnaam']} staat onder {len(gevonden)} merken in {z.naam}: "
                          + ", ".join(f"{a.get('profiel') or 'merk'} (nummer {a['id']})" for a in gevonden))
        elif gevonden[0]["id"] not in {a["id"] for a in kies}:
            kies.append(gevonden[0])
    if mist:
        sys.exit(f"Niet gevonden in {z.naam}: {', '.join(mist)}. Koppel ze eerst of kijk de naam na.")
    if dubbel:
        sys.exit("\n".join(dubbel) + ". Kies het merk waarop je wilt posten met zijn nummer, bijvoorbeeld: koppel.py --gebruik "
                 + dubbel[0].split("(nummer ")[1].split(")")[0])
    MIJN.mkdir(parents=True, exist_ok=True)
    if ACCOUNTS.exists():
        shutil.copy2(ACCOUNTS, vrije_naam(MIJN / "oud", "accounts", ".json"))
    ACCOUNTS.write_text(json.dumps([{"id": a["id"], "gebruikersnaam": a["gebruikersnaam"]} for a in kies],
                                   indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("In gebruik: " + ", ".join("@" + a["gebruikersnaam"] + (f" (merk {a.get('profiel') or a['id']})" if z.naam == "Metricool" else "")
                                     for a in kies))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--link", action="store_true")
    ap.add_argument("--gebruik", nargs="+", metavar="NAAM")
    ap.add_argument("--erbij", nargs="+", metavar="NAAM")
    a = ap.parse_args()
    try:
        z = maak_koppeling(laad())
        if a.link:
            link(z)
        elif a.gebruik or a.erbij:
            gebruik(z, a.gebruik or a.erbij, erbij=bool(a.erbij))
        else:
            toon(z)
    except (KoppelFout, InstellingFout) as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
