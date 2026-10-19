#!/usr/bin/env python3
"""
Zet de koppeling om te posten: bewaart de sleutel van Zernio of de token van Metricool op deze
computer, buiten het project, en onthoudt welke koppeling deze gebruiker heeft.

    python3 engine/scripts/sleutel.py                               Zernio: vraagt de sleutel (je ziet hem niet)
    printf '%s' 'sk_...' | python3 engine/scripts/sleutel.py
    printf '%s' '<token>' | python3 engine/scripts/sleutel.py --metricool --user 1234567
    python3 engine/scripts/sleutel.py --zelf                          geen koppeling: zelf posten met een ander programma
    python3 engine/scripts/sleutel.py --bewaard zernio|metricool      terug naar een koppeling waarvan de sleutel of
                                                                      token hier al bewaard is (geen nieuwe nodig)

De sleutel of token komt in ~/.config/trial-reels-starter/, alleen leesbaar voor jou. Eerst wordt
hij geprobeerd; een sleutel die niet werkt, wordt niet bewaard. Een vorige blijft ernaast staan
als <naam>.oud-<datum>. De keuze (zernio of metricool) komt in mijn-trial-reels/koppeling.json.
"""

import argparse
import getpass
import os
import re
import sys

import koppeling
from instellingen import InstellingFout, laad, vrije_naam
from koppelfout import KoppelFout


def bewaar(bestand, waarde):
    bestand.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(bestand.parent, 0o700)
    if bestand.exists():
        bestand.rename(vrije_naam(bestand.parent, f"{bestand.name}.oud", ""))
    fd = os.open(bestand, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(waarde + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--metricool", action="store_true", help="de token van Metricool in plaats van een Zernio-sleutel")
    ap.add_argument("--user", help="het Metricool-gebruikersnummer (userId), te vinden bij de API-instellingen in Metricool")
    ap.add_argument("--zelf", action="store_true", help="geen koppeling: de gebruiker post zelf met een ander programma")
    ap.add_argument("--bewaard", choices=["zernio", "metricool"], help="wissel naar deze koppeling met de sleutel of token die hier al staat")
    a = ap.parse_args()
    if a.bewaard:
        try:
            vorige = koppeling.lees()
            if a.bewaard == "zernio":
                from zernio import Zernio
                aantal = len(Zernio().accounts())
                koppeling.schrijf({"soort": "zernio"})
            else:
                from metricool import Metricool
                user = a.user or vorige.get("metricool_user")
                aantal = len(Metricool(user_id=user, tijdzone=laad()["posten"]["tijdzone"]).accounts())
                koppeling.schrijf({"soort": "metricool", "metricool_user": str(user)})
        except (KoppelFout, InstellingFout) as e:
            sys.exit(str(e))
        print(f"De koppeling is nu {'Zernio' if a.bewaard == 'zernio' else 'Metricool'}, met de sleutel die hier al stond: hij werkt "
              f"({aantal} Instagram-account(s)). Kijk met koppel.py welke accounts in gebruik zijn.")
        return
    if a.zelf:
        koppeling.schrijf({"soort": "zelf"})
        print("Geen koppeling: je post zelf. De starter maakt de reels; inplannen en cijfers doe je in je eigen programma.")
        return
    waarde = (getpass.getpass("Sleutel: ") if sys.stdin.isatty() else sys.stdin.read()).strip()
    if a.metricool:
        from metricool import TOKENBESTAND, Metricool
        if not a.user or not a.user.isdigit():
            sys.exit("Geef ook het Metricool-gebruikersnummer mee: --user 1234567 (alleen cijfers). Het staat in Metricool bij de API-instellingen.")
        if not re.fullmatch(r"[A-Za-z0-9_\-]{16,200}", waarde):
            sys.exit("Dit lijkt geen Metricool-token. Kopieer hem opnieuw uit Metricool (instellingen, API).")
        try:
            tijdzone = laad()["posten"]["tijdzone"]
            aantal = len(Metricool(user_id=a.user, tijdzone=tijdzone, token=waarde).accounts())
        except InstellingFout as e:
            sys.exit(str(e))
        except KoppelFout as e:
            sys.exit("Metricool neemt deze token of dit gebruikersnummer niet aan. Kijk ze na in Metricool; de API zit in het "
                     "Advanced-abonnement en hoger." if e.status in (401, 403) else str(e))
        bewaar(TOKENBESTAND, waarde)
        koppeling.schrijf({"soort": "metricool", "metricool_user": a.user})
        print(f"Token bewaard en hij werkt: Metricool ziet {aantal} merk(en) met een Instagram-account. De koppeling is nu Metricool.")
        return
    from zernio import SLEUTEL_RE, SLEUTELBESTAND, Zernio
    if not SLEUTEL_RE.match(waarde):
        sys.exit("Dit is geen Zernio-sleutel: die begint met sk_ en heeft daarna 64 tekens. Kopieer hem opnieuw uit Zernio.")
    try:
        aantal = len(Zernio(sleutel=waarde).accounts())
    except KoppelFout as e:
        sys.exit("Zernio neemt deze sleutel niet aan. Maak in Zernio een nieuwe." if e.status == 401 else str(e))
    bewaar(SLEUTELBESTAND, waarde)
    koppeling.schrijf({"soort": "zernio"})
    print(f"Sleutel bewaard en hij werkt: Zernio ziet {aantal} Instagram-account(s). De koppeling is nu Zernio.")


if __name__ == "__main__":
    main()
