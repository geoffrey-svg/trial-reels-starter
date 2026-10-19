#!/usr/bin/env python3
"""
De cijfers van alle reels die deze starter inplande, en welke winners zijn.

    python3 engine/scripts/cijfers.py               de laatste 30 dagen
    python3 engine/scripts/cijfers.py --dagen 90

Een reel telt pas mee na 48 uur: daarvoor zijn de cijfers van Instagram nog niet af.
Een winner haalt minstens <factor> keer de gewone views van zijn eigen account
(de mediaan, apart voor trial reels en gewone reels, want gewone reels zien ook de volgers)
en minstens <min_views> views; beide staan in de instellingen. Views tussen accounts
vergelijken zegt weinig, want een groter account haalt nu eenmaal meer.

Het verslag komt in mijn-trial-reels/cijfers/cijfers-<datum>.md.
"""

import argparse
import json
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from instellingen import MIJN, InstellingFout, laad
from planning import nl
from koppelfout import KoppelFout
from koppeling import maak as maak_koppeling

RIJP_NA = timedelta(hours=48)
GEEN_BEREIK_NA = 5     # zoveel rijpe reels zonder enig bereik op een account is een signaal


def ingepland():
    """Alles wat deze starter inplande, op het id bij de koppeling, met de ronde en de tekst erbij."""
    uit = {}
    for boek in sorted((MIJN / "rondes").glob("*/ingepland.json")):
        ronde_map = boek.parent
        try:
            ronde = json.loads((ronde_map / "ronde.json").read_text(encoding="utf-8"))
            posts = json.loads(boek.read_text(encoding="utf-8")).get("posts", {})
        except (OSError, json.JSONDecodeError):
            continue
        bron = {p.get("id"): p for p in ronde.get("posts", [])}
        for pid, regel in posts.items():
            if regel.get("zernio_id"):
                p = bron.get(pid, {})
                uit[regel["zernio_id"]] = {"ronde": ronde_map.name, "id": pid, "account": regel.get("account"),
                                           "gebruikersnaam": regel.get("gebruikersnaam"), "soort": regel.get("soort"),
                                           "tekst": p.get("tekst") or "", "caption": p.get("caption") or "",
                                           "angle": p.get("angle") or ""}
    return uit


def verzamel(z, eigen, dagen, nu):
    vanaf = (nu - timedelta(days=dagen)).date().isoformat()
    reels = []
    for account in sorted({e["account"] for e in eigen.values() if e.get("account")}):
        for post in z.cijfers(account, vanaf):
            info = eigen.get(post.get("latePostId")) or eigen.get(post.get("_id"))
            if not info or not post.get("publishedAt"):
                continue
            m = post.get("analytics") or {}
            gepost = datetime.fromisoformat(post["publishedAt"].replace("Z", "+00:00"))
            reels.append({**info, "gepost": gepost, "rijp": nu - gepost >= RIJP_NA,
                          "url": post.get("platformPostUrl") or "",
                          "views": m.get("views"), "bereik": m.get("reach"), "likes": m.get("likes"),
                          "reacties": m.get("comments"), "shares": m.get("shares"), "saves": m.get("saves"),
                          "kijktijd": m.get("igReelsAvgWatchTime"), "skip": m.get("reelsSkipRate")})
    return reels


def beoordeel(reels, winners):
    """Zet per reel de verhouding tot de mediaan van zijn account (per soort), en of hij een winner is.
    Geeft de medianen per (account, soort) terug."""
    per_groep = {}
    for r in reels:
        if r["rijp"] and isinstance(r["views"], (int, float)):
            per_groep.setdefault((r["account"], r["soort"]), []).append(r["views"])
    medianen = {g: statistics.median(v) for g, v in per_groep.items()}
    for r in reels:
        med = medianen.get((r["account"], r["soort"]))
        # Een mediaan van 0 (bijna niets kreeg views) telt als 1: een reel met veel views is daar juist een winner
        r["keer"] = (r["views"] / max(med, 1)) if (r["rijp"] and med is not None and isinstance(r["views"], (int, float))) else None
        r["winner"] = bool(r["keer"] is not None and r["keer"] >= winners["factor"] and r["views"] >= winners["min_views"])
    return medianen


def getal(v):
    if v is None:
        return "-"
    return f"{v / 1000:.1f}k".replace(".0k", "k") if v >= 10000 else str(int(v))


def verslag(reels, medianen, cfg, nu):
    tz = ZoneInfo(cfg["posten"]["tijdzone"])
    w = cfg["winners"]
    namen = {r["account"]: r["gebruikersnaam"] for r in reels}
    rijp = [r for r in reels if r["rijp"]]
    regels = [f"# Cijfers trial reels, {nl(nu.astimezone(tz))} {nu.astimezone(tz).year}", "",
              f"{len(reels)} reels gevonden, waarvan {len(rijp)} ouder dan 48 uur. "
              f"Winner: minstens {w['factor']} keer de mediaan van het eigen account en minstens {w['min_views']} views.", ""]
    regels += ["## Per account", "", "| account | soort | reels (rijp) | mediaan views |", "|---|---|---|---|"]
    for a, soort in sorted({(r["account"], r["soort"]) for r in reels}, key=lambda x: (namen.get(x[0]) or "", x[1] or "")):
        alle = [r for r in reels if r["account"] == a and r["soort"] == soort]
        regels.append(f"| @{namen.get(a)} | {'trial' if soort == 'trial' else 'gewoon'} | {len(alle)} ({sum(1 for r in alle if r['rijp'])}) "
                      f"| {getal(medianen.get((a, soort)))} |")
    stil = sorted({a for (a, _s), med in medianen.items() if med == 0
                   and sum(1 for r in rijp if r["account"] == a and r["views"] == 0 and r["bereik"] == 0) >= GEEN_BEREIK_NA})
    if stil:
        regels += ["", "Let op: " + ", ".join("@" + (namen.get(a) or "?") for a in stil) +
                   " heeft op de laatste reels 0 views en 0 bereik. Kijk in de Instagram-app of die reels echt geen views hebben."
                   " Is dat zo, dan laat Instagram ze aan niemand zien: post er een paar dagen minder op en kijk of het terugkomt."
                   " Hebben ze in de app wel views, dan loopt de koppeling achter met de cijfers."]
    win = sorted([r for r in reels if r["winner"]], key=lambda r: -r["keer"])
    regels += ["", f"## Winners ({len(win)})", ""]
    if not win:
        regels.append("Nog geen winners." if rijp else "Nog niets ouder dan 48 uur; kijk over een paar dagen opnieuw.")
    for n, r in enumerate(win, 1):
        regels.append(f"{n}. **{r['keer']:.1f}x** @{r['gebruikersnaam']}, {getal(r['views'])} views, "
                      f"{getal(r['shares'])} shares, {getal(r['saves'])} saves. Ronde {r['ronde']}, post {r['id']}"
                      f"{', angle ' + r['angle'] if r['angle'] else ''}. Tekst: {r['tekst'] or '(geen)'}. {r['url']}")
    hoeken = {}
    for r in rijp:
        if r["angle"] and r["keer"] is not None:
            hoeken.setdefault(r["angle"], []).append(r["keer"])
    if hoeken:
        regels += ["", "## Per angle (mediaan van keer de mediaan van het account)", "", "| angle | reels | keer |", "|---|---|---|"]
        for h, v in sorted(hoeken.items(), key=lambda kv: -statistics.median(kv[1])):
            regels.append(f"| {h} | {len(v)} | {statistics.median(v):.2f} |")
    regels += ["", "## Alle reels, beste eerst", "",
               "| keer | views | bereik | likes | reacties | shares | saves | account | gepost | post | tekst |",
               "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(reels, key=lambda r: (r["keer"] is None, -(r["keer"] or 0), -(r["views"] or 0))):
        keer = "nog niet" if not r["rijp"] else ("-" if r["keer"] is None else f"{r['keer']:.1f}")
        tekst = (r["tekst"] or r["caption"]).replace("\n", " ").replace("|", "/")[:50]
        regels.append(f"| {keer} | {getal(r['views'])} | {getal(r['bereik'])} | {getal(r['likes'])} | {getal(r['reacties'])} "
                      f"| {getal(r['shares'])} | {getal(r['saves'])} | @{r['gebruikersnaam']} | {nl(r['gepost'].astimezone(tz), dag=False)} "
                      f"| {r['ronde']}/{r['id']} | {tekst} |")
    regels += ["", "Een winner zet je op je hoofdaccount als nieuwe video, niet als hetzelfde bestand: Instagram geeft "
               "hergebruikte content minder bereik."]
    return "\n".join(regels) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dagen", type=int, default=30)
    a = ap.parse_args()
    try:
        cfg = laad()
        eigen = ingepland()
        if not eigen:
            sys.exit("Er is nog niets ingepland met deze starter, dus er zijn nog geen cijfers.")
        nu = datetime.now(timezone.utc)
        reels = verzamel(maak_koppeling(cfg), eigen, max(1, min(a.dagen, 366)), nu)
        medianen = beoordeel(reels, cfg["winners"])
        tekst = verslag(reels, medianen, cfg, nu)
    except (InstellingFout, KoppelFout) as e:
        sys.exit(str(e))
    map_ = MIJN / "cijfers"
    map_.mkdir(parents=True, exist_ok=True)
    uit = map_ / f"cijfers-{nu.astimezone(ZoneInfo(cfg['posten']['tijdzone'])):%Y-%m-%d-%H%M}.md"
    uit.write_text(tekst, encoding="utf-8")
    winners = sum(1 for r in reels if r["winner"])
    print(f"{len(reels)} reels, {winners} winner(s). Verslag: {uit}")


if __name__ == "__main__":
    main()
