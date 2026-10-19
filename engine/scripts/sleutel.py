#!/usr/bin/env python3
"""
Bewaart de Zernio-sleutel op deze computer, buiten het project.

    python3 engine/scripts/sleutel.py              vraagt de sleutel (je ziet hem niet tijdens het typen)
    printf '%s' 'sk_...' | python3 engine/scripts/sleutel.py

De sleutel komt in ~/.config/trial-reels-starter/zernio-api-key, alleen leesbaar voor
jou. Eerst wordt hij bij Zernio geprobeerd; een sleutel die niet werkt, wordt niet bewaard.
Een vorige sleutel blijft ernaast staan als zernio-api-key.oud-<datum>.
"""

import getpass
import os
import sys

from instellingen import vrije_naam
from zernio import SLEUTEL_RE, SLEUTELBESTAND, Zernio, ZernioFout


def main():
    sleutel = (getpass.getpass("Zernio-sleutel: ") if sys.stdin.isatty() else sys.stdin.read()).strip()
    if not SLEUTEL_RE.match(sleutel):
        sys.exit("Dit is geen Zernio-sleutel: die begint met sk_ en heeft daarna 64 tekens. Kopieer hem opnieuw uit Zernio.")
    try:
        aantal = len(Zernio(sleutel=sleutel).accounts())
    except ZernioFout as e:
        sys.exit("Zernio neemt deze sleutel niet aan. Maak in Zernio een nieuwe." if e.status == 401 else str(e))
    SLEUTELBESTAND.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(SLEUTELBESTAND.parent, 0o700)
    if SLEUTELBESTAND.exists():
        SLEUTELBESTAND.rename(vrije_naam(SLEUTELBESTAND.parent, f"{SLEUTELBESTAND.name}.oud", ""))
    fd = os.open(SLEUTELBESTAND, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(sleutel + "\n")
    print(f"Sleutel bewaard en hij werkt: Zernio ziet {aantal} Instagram-account(s).")


if __name__ == "__main__":
    main()
