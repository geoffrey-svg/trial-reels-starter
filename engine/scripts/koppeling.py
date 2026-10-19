"""
Welke koppeling deze gebruiker heeft om te posten: Zernio of Metricool.

De keuze staat in mijn-trial-reels/koppeling.json, gezet door sleutel.py:
    {"soort": "zernio"}, {"soort": "metricool", "metricool_user": "1234567"} of {"soort": "zelf"}
Zonder dat bestand is het Zernio. "zelf" betekent: de gebruiker post met een ander programma
(of de Instagram-app); dan maakt de starter alleen de reels en plant hij niets in.
"""

import json

from instellingen import MIJN
from koppelfout import KoppelFout

BESTAND = MIJN / "koppeling.json"
SOORTEN = ("zernio", "metricool", "zelf")


def lees():
    try:
        k = json.loads(BESTAND.read_text(encoding="utf-8")) if BESTAND.exists() else {}
    except json.JSONDecodeError:
        raise KoppelFout(f"{BESTAND} is geen geldig bestand. Zet de koppeling opnieuw met sleutel.py.")
    k.setdefault("soort", "zernio")
    if k["soort"] not in SOORTEN:
        raise KoppelFout(f"Onbekende koppeling {k['soort']!r} in {BESTAND}.")
    return k


def schrijf(k):
    """Bewaart de keuze. Wat er al stond (zoals het Metricool-gebruikersnummer) blijft, zodat terugwisselen kan
    zonder alles opnieuw te vragen."""
    try:
        oud = lees() if BESTAND.exists() else {}
    except KoppelFout:
        oud = {}
    MIJN.mkdir(parents=True, exist_ok=True)
    BESTAND.write_text(json.dumps({**oud, **k}, indent=2) + "\n", encoding="utf-8")


def maak(cfg):
    """De koppeling van deze gebruiker, klaar voor gebruik."""
    k = lees()
    if k["soort"] == "zelf":
        raise KoppelFout("Je post zelf, met een ander programma of de Instagram-app. Inplannen en cijfers via de starter kan dan "
                         "niet: de reels staan klaar in de map klaar/ van de ronde. Wil je toch een koppeling, zet die dan met sleutel.py.")
    if k["soort"] == "metricool":
        from metricool import Metricool
        return Metricool(user_id=k.get("metricool_user"), tijdzone=cfg["posten"]["tijdzone"])
    from zernio import Zernio
    return Zernio()
