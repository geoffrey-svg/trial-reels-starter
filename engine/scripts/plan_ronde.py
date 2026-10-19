#!/usr/bin/env python3
"""
Plant de reels van een ronde in als trial reel, via de koppeling van de gebruiker (Zernio of Metricool).

    python3 engine/scripts/plan_ronde.py <ronde>             voorstel: wanneer gaat elke reel, verandert niets
    python3 engine/scripts/plan_ronde.py <ronde> --echt      zet het voorstel echt klaar (alleen na een ja van de gebruiker)
    python3 engine/scripts/plan_ronde.py <ronde> --stand     hoe staat het: gepland, online of mislukt

Opties bij het voorstel:
    --soort auto|trial|gewoon   auto (standaard): trial reel vanaf 200 volgers, daaronder een gewone reel
    --vanaf JJJJ-MM-DD          niet eerder beginnen dan deze dag

Het voorstel staat daarna in <ronde>/voorstel.json; --echt zet precies dat klaar, en weigert
als er sinds het voorstel iets veranderd is (een reel, een caption, de postregels of wat er bij
de koppeling staat). Wat al klaarstaat, staat in <ronde>/ingepland.json. Stopt het halverwege, draai
dan --echt opnieuw: wat er al stond, wordt niet nog een keer gepland. Er loopt nooit twee keer
tegelijk iets op dezelfde ronde. --echt kan minuten duren (uploaden): geef het ruim de tijd.

Een reel die bij de koppeling mislukte of die de gebruiker daar stopte, neemt een nieuw voorstel
opnieuw mee. Reels die via een andere koppeling gingen (van voor een wissel), tellen mee als bezet
op hetzelfde Instagram-account.
"""

import argparse
import json
import os
import signal
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from instellingen import MIJN, InstellingFout, laad
from koppelfout import KoppelFout
from koppeling import maak as maak_koppeling
from maak_reels import RondeFout, actueel, lees_ronde, vingerafdruk
from planning import PlanFout, nl, past, plan
from slot import SlotFout, slot
from zernio import instagram_deel

ACCOUNTS = MIJN / "accounts.json"
TRIAL_VANAF = 200   # Instagram Help Center: trial reels vanaf 200 volgers op een publiek professioneel account


def lees_json(pad, leeg):
    return json.loads(Path(pad).read_text(encoding="utf-8")) if Path(pad).exists() else leeg


def schrijf_json(pad, data):
    """Eerst naar een eigen hulpbestand, dan pas op zijn plek: een onderbreking laat nooit een half bestand achter."""
    pad = Path(pad)
    hulp = pad.with_name(f".{pad.name}.{os.getpid()}.tmp")
    hulp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    hulp.replace(pad)


def tijd_van(tekst):
    return datetime.fromisoformat(tekst.replace("Z", "+00:00"))


def eigen_accounts():
    lijst = lees_json(ACCOUNTS, [])
    if not lijst:
        raise PlanFout("Er staat nog geen account klaar. Kies er een met: python3 engine/scripts/koppel.py --gebruik <naam>")
    return lijst


def koppeling_van(regel):
    return regel.get("koppeling", "Zernio")    # versie 1.0 kende alleen Zernio


def bezette_tijden(z, agenda, namen, behalve=()):
    """Wat er al gepland of net gepost is op elk account: van deze starter én wat de gebruiker zelf in Zernio of
    Metricool zette (agenda: {account: [(post-id, tijd)]} van z.bezet). De posts in behalve tellen niet.
    Reels van deze starter via een andere koppeling (van voor een wissel) ziet de koppeling van nu niet; die tellen
    mee op het account met dezelfde Instagram-naam."""
    bezet = {a: [t for pid, t in lijst if pid not in behalve] for a, lijst in agenda.items()}
    op_naam = {str(n).lower(): a for a, n in namen.items()}
    grens = datetime.now(timezone.utc) - timedelta(days=2)
    for boek in sorted((MIJN / "rondes").glob("*/ingepland.json")):
        try:
            regels = lees_json(boek, {}).get("posts", {}).values()
        except (OSError, json.JSONDecodeError):
            continue
        for r in regels:
            a = op_naam.get(str(r.get("gebruikersnaam") or "").lower())
            if (a in bezet and r.get("zernio_id") and r.get("tijd") and koppeling_van(r) != z.naam
                    and r.get("status") not in ("failed", "cancelled", "weg") and tijd_van(r["tijd"]) > grens):
                bezet[a].append(tijd_van(r["tijd"]))
    return bezet


def opnieuw_vrij(z, boek, agenda):
    """Reels uit het boek die niet meer online gaan: gestopt in de koppeling, mislukt, of een concept. Die mogen opnieuw
    in een voorstel (met een nieuwe eigen sleutel); wat er stond, gaat naar 'eerder'. Alleen als de koppeling dat zelf
    bevestigt: een post die er nog staat, blijft staan. Geeft de ids terug."""
    in_agenda = {pid for lijst in agenda.values() for pid, _ in lijst}
    vrij = []
    for pid, regel in list(boek["posts"].items()):
        if (not regel.get("zernio_id") or koppeling_van(regel) != z.naam or regel.get("status") == "published"
                or regel["zernio_id"] in in_agenda):
            continue
        try:
            post = z.post(regel["zernio_id"], regel.get("account"))
            status = "concept" if post.get("draft") else instagram_deel(post).get("status") or post.get("status")
        except KoppelFout as e:
            if e.status != 404:
                raise
            status = "weg"
        if status in ("failed", "cancelled", "weg", "concept"):
            oud = {k: v for k, v in regel.items() if k != "eerder"}
            boek["posts"][pid] = {"eerder": regel.get("eerder", []) + [{**oud, "status": status}]}
            vrij.append(pid)
        else:
            regel["status"] = status
    return vrij


def kies_soort(account, soort, koppeling="Zernio"):
    volgers = account.get("volgers")
    if soort == "gewoon":
        return "gewoon"
    if soort == "trial":
        if volgers is not None and volgers < TRIAL_VANAF:
            raise PlanFout(f"@{account['gebruikersnaam']} heeft {volgers} volgers; Instagram staat trial reels pas toe vanaf {TRIAL_VANAF}.")
        return "trial"
    if volgers is None:
        raise PlanFout(f"{koppeling} weet niet hoeveel volgers @{account['gebruikersnaam']} heeft. "
                       "Vraag de gebruiker of het account al 200 volgers heeft en kies dan --soort trial of --soort gewoon.")
    return "trial" if volgers >= TRIAL_VANAF else "gewoon"


def neem_over(regel, post):
    """Een post die bij de koppeling staat, in het boek: id, stand, en de tijd en het account zoals ze daar echt zijn."""
    ig = instagram_deel(post)
    regel["zernio_id"] = post["_id"]
    regel["status"] = ig.get("status") or post.get("status", "scheduled")
    if post.get("scheduledFor"):
        regel["tijd"] = tijd_van(post["scheduledFor"]).isoformat()
    account = ig.get("accountId")
    if isinstance(account, dict):
        account = account.get("_id")
    if account:
        regel["account"] = account
    if "isTrialReel" in ig:
        regel["soort"] = "trial" if ig.get("isTrialReel") else "gewoon"


def zoek_verweesd(z, boek):
    """Kwam een eerdere poging wel aan maar het antwoord niet, dan staat de post al bij de koppeling (Zernio: met zijn
    eigen sleutel als tag; Metricool: op dezelfde minuut met dezelfde caption).
    Die gaat dan in het boek, zodat geen voorstel hem nog een keer plant. Geeft de overgenomen post-ids terug."""
    gevonden = []
    for pid, regel in boek["posts"].items():
        if regel.get("sleutel") and not regel.get("zernio_id") and koppeling_van(regel) == z.naam:
            al = z.zoek(regel)
            if al:
                neem_over(regel, al[0])
                gevonden.append(pid)
    return gevonden


def voorstel(map_, ronde, cfg, z, soort, vanaf):
    map_ = Path(map_)
    eigen = eigen_accounts()
    in_zernio = {a["id"]: a for a in z.accounts()}
    accounts = []
    for a in eigen:
        zo = in_zernio.get(a["id"])
        if not zo:
            raise PlanFout(f"@{a['gebruikersnaam']} staat niet meer in {z.naam}. Koppel het opnieuw (zie koppel.py).")
        if not zo["gezond"]:
            raise PlanFout(f"De koppeling van @{zo['gebruikersnaam']} moet vernieuwd of voor posten aangezet worden in {z.naam}. Doe dat en probeer het opnieuw.")
        accounts.append(zo)
    op_naam = {a["gebruikersnaam"].lower(): a["id"] for a in accounts}
    namen = {a["id"]: a["gebruikersnaam"] for a in accounts}
    boek_pad = map_ / "ingepland.json"
    boek = lees_json(boek_pad, {"posts": {}})
    for p in ronde["posts"]:
        r = boek["posts"].get(p["id"], {})
        if r.get("sleutel") and not r.get("zernio_id") and koppeling_van(r) != z.naam:
            raise PlanFout(f"Reel {p['id']} werd eerder via {koppeling_van(r)} ingepland, maar het antwoord kwam niet aan: misschien "
                           f"staat hij daar al. Zet de koppeling eerst terug op {koppeling_van(r)} (sleutel.py --bewaard "
                           f"{koppeling_van(r).lower()}) en maak daar het voorstel; dan zoekt de starter hem terug.")
    verweesd = zoek_verweesd(z, boek)
    agenda = {a["id"]: z.bezet(a["id"]) for a in accounts}
    opnieuw = opnieuw_vrij(z, boek, agenda)
    if verweesd or opnieuw:
        schrijf_json(boek_pad, boek)
    nog_stoppen = sorted(pid for pid, r in boek["posts"].items() if r.get("zernio_id") and r.get("fout")
                         and koppeling_van(r) == z.naam and r.get("status") != "published")
    posts, niet_actueel = [], []
    for p in ronde["posts"]:
        if boek["posts"].get(p["id"], {}).get("zernio_id"):
            continue
        if not actueel(map_, p, cfg):
            niet_actueel.append(p["id"])
        vast = p.get("account")
        if vast is not None and str(vast).lstrip("@").lower() not in op_naam:
            raise PlanFout(f"Post {p['id']} moet naar @{str(vast).lstrip('@')}, maar dat account is niet in gebruik.")
        posts.append((p["id"], op_naam[str(vast).lstrip("@").lower()] if vast is not None else None))
    if niet_actueel:
        raise PlanFout(f"Deze reels zijn nog niet (opnieuw) gemaakt sinds de tekst, het stuk video of de stijl veranderde: "
                       f"{', '.join(niet_actueel)}. Draai eerst maak_reels.py.")
    if not posts:
        if nog_stoppen:
            raise PlanFout(f"Er valt nu niets in te plannen. Reel {', '.join(nog_stoppen)} staat nog in {z.naam} met een fout: "
                           f"de gebruiker stopt die post daar eerst, daarna neemt een nieuw voorstel hem opnieuw mee.")
        raise PlanFout(f"Alle reels van deze ronde staan al klaar bij {z.naam}. Kijk hoe het gaat met --stand.")
    soorten = {a["id"]: kies_soort(a, soort, z.naam) for a in accounts}
    eigen_ids = {e.get("zernio_id") for e in boek["posts"].values() if e.get("zernio_id")}
    # De eigen posts van deze ronde die al bij de koppeling staan, tellen gewoon mee als bezet
    bezet = bezette_tijden(z, agenda, namen)
    nu = datetime.now(timezone.utc)
    rij = plan(posts, [a["id"] for a in accounts], bezet, cfg["posten"], nu, vanaf, marge=z.marge_minuten)
    bron = {p["id"]: p for p in ronde["posts"]}
    return {
        "gemaakt": nu.isoformat(),
        "koppeling": z.naam,
        "tijdzone": cfg["posten"]["tijdzone"],
        "doorzetten": cfg["posten"]["doorzetten"],
        "posten": cfg["posten"],
        "al_ingepland": sorted(eigen_ids),
        "opnieuw": sorted(opnieuw),
        "nog_stoppen": nog_stoppen,
        "posts": [{"id": pid, "account": a, "gebruikersnaam": namen[a], "tijd": t.isoformat(), "soort": soorten[a],
                   "caption": bron[pid].get("caption", ""), "reel": vingerafdruk(bron[pid], cfg)}
                  for pid, a, t in rij],
    }


def toon_voorstel(v, ronde, boek):
    tz = ZoneInfo(v["tijdzone"])
    via = v.get("koppeling", "Zernio")
    teksten = {p["id"]: (p.get("tekst") or p.get("caption") or "").replace("\n", " ")[:50] for p in ronde["posts"]}
    al = [(pid, r) for pid, r in boek["posts"].items() if r.get("zernio_id")]
    if al:
        print(f"Al bij {via} uit deze ronde ({len(al)}), die blijven zoals ze staan:")
        for pid, r in sorted(al, key=lambda x: x[1].get("tijd", "")):
            fout = f"  MISLUKT, eerst stoppen in {via}: {r['fout']}" if pid in v.get("nog_stoppen", []) else ""
            elders = f"  (via {koppeling_van(r)})" if koppeling_van(r) != via else ""
            print(f"  {nl(tijd_van(r['tijd']).astimezone(tz)):<16}  @{r.get('gebruikersnaam', '?')}  {pid}{elders}{fout}")
        print()
    if v.get("opnieuw"):
        print(f"Opnieuw in dit voorstel, want gestopt of mislukt bij {via}: {', '.join(v['opnieuw'])}.\n")
    regels = []
    for p in v["posts"]:
        t = datetime.fromisoformat(p["tijd"]).astimezone(tz)
        regels.append(f"{nl(t):<16}  @{p['gebruikersnaam']:<22} {'trial reel' if p['soort'] == 'trial' else 'GEWONE reel':<12} {p['id']}  {teksten.get(p['id'], '')}")
    gewoon = sorted({p["gebruikersnaam"] for p in v["posts"] if p["soort"] == "gewoon"})
    eerste = datetime.fromisoformat(v["posts"][0]["tijd"]).astimezone(tz)
    laatste = datetime.fromisoformat(v["posts"][-1]["tijd"]).astimezone(tz)
    print(f"Voorstel: {len(v['posts'])} reels van {nl(eerste)} tot {nl(laatste)} ({v['tijdzone']}), via {via}.")
    print("\n".join(regels))
    if any(p["soort"] == "trial" for p in v["posts"]):
        print("\nDoorzetten naar volgers: " + ("Instagram laat een trial reel die goed loopt vanzelf aan de volgers zien."
                                              if v["doorzetten"] == "automatisch" else "doet de gebruiker zelf in de Instagram-app."))
    if gewoon:
        print(f"\nLet op: op {', '.join('@' + g for g in gewoon)} gaan GEWONE reels, die ook de volgers zien "
              f"(minder dan {TRIAL_VANAF} volgers, of zo gekozen).")
    print("\nVan dit voorstel is nog niets ingepland. Zegt de gebruiker ja, draai dan: plan_ronde.py <ronde> --echt")


def echt(map_, ronde, cfg, z):
    map_ = Path(map_)
    v = lees_json(map_ / "voorstel.json", None)
    if not v:
        raise PlanFout("Er is nog geen voorstel. Draai eerst plan_ronde.py zonder --echt en laat het zien.")
    verouderd = "Het voorstel is verouderd: {}. Maak een nieuw voorstel en laat het zien."
    if v.get("koppeling", "Zernio") != z.naam:
        raise PlanFout(verouderd.format(f"de koppeling is nu {z.naam}"))
    if v.get("posten") != cfg["posten"]:
        raise PlanFout(verouderd.format("de postregels zijn veranderd"))
    boek_pad = map_ / "ingepland.json"
    boek = lees_json(boek_pad, {"posts": {}})
    # Wat uit deze ronde al bij Zernio stond, moet nog hetzelfde zijn als bij het voorstel (posts van dit voorstel zelf, van
    # een eerdere poging die halverwege stopte, tellen niet: die horen er juist bij)
    in_voorstel = {p["id"] for p in v["posts"]}
    buiten = {e["zernio_id"] for pid, e in boek["posts"].items() if e.get("zernio_id") and pid not in in_voorstel}
    if set(v.get("al_ingepland", [])) != buiten:
        raise PlanFout(verouderd.format(f"er is sinds het voorstel iets bijgekomen bij {z.naam}"))
    bron = {p["id"]: p for p in ronde["posts"]}
    open_ = [p for p in v["posts"] if not boek["posts"].get(p["id"], {}).get("zernio_id")]
    for p in open_:
        b = bron.get(p["id"])
        if not b or b.get("caption", "") != p["caption"] or vingerafdruk(b, cfg) != p["reel"] or not actueel(map_, b, cfg):
            raise PlanFout(verouderd.format(f"reel {p['id']} of zijn caption is veranderd"))
    # 1. Kwam een eerdere poging wel aan maar het antwoord niet, dan hoort die post er gewoon bij
    for pid in zoek_verweesd(z, boek):
        schrijf_json(boek_pad, boek)
        r = boek["posts"][pid]
        print(f"al bij {z.naam}: {pid} op {nl(tijd_van(r['tijd']).astimezone(ZoneInfo(v['tijdzone'])))} (van een eerdere poging)")
    open_ = [p for p in open_ if not boek["posts"].get(p["id"], {}).get("zernio_id")]
    if not open_:
        print(f"Alles uit dit voorstel staat al klaar bij {z.naam}. Kijk hoe het gaat met --stand.")
        return
    # 2. Alles moet nog in de toekomst liggen, en er mag intussen niets anders op die plekken staan
    nu = datetime.now(timezone.utc)
    if any(datetime.fromisoformat(p["tijd"]) - nu < z.min_vooruit_voorstel for p in open_):
        raise PlanFout(verouderd.format("een tijd ligt (bijna) in het verleden"))
    eigen_ids = {e.get("zernio_id") for e in boek["posts"].values()}
    namen = {p["account"]: p["gebruikersnaam"] for p in open_}
    bezet = bezette_tijden(z, {a: z.bezet(a) for a in sorted(namen)}, namen, behalve=eigen_ids)
    for e in boek["posts"].values():
        if e.get("zernio_id") and e.get("tijd") and e.get("account") in bezet:
            bezet[e["account"]].append(tijd_van(e["tijd"]))
    gepland = {}
    for p in open_:
        t = datetime.fromisoformat(p["tijd"])
        if not past(t, p["account"], {p["account"]: bezet.get(p["account"], []) + gepland.get(p["account"], [])}, cfg["posten"]):
            raise PlanFout(verouderd.format(f"er is intussen iets anders ingepland op @{p['gebruikersnaam']}"))
        gepland.setdefault(p["account"], []).append(t)
    # 3. Inplannen, en na elke stap opschrijven wat er al is
    klaar, mislukt = 0, []
    with z.media([map_ / "klaar" / f"{p['id']}.mp4" for p in open_]):
        for p in open_:
            regel = boek["posts"].setdefault(p["id"], {})
            regel.setdefault("sleutel", uuid.uuid4().hex)
            regel.update({k: p[k] for k in ("account", "gebruikersnaam", "tijd", "soort", "caption")})
            regel.update(reel=p["reel"], koppeling=z.naam)
            schrijf_json(boek_pad, boek)
            # Bij Zernio blijft een geüploade video staan; bij Metricool hoort het adres bij de tunnel van nu
            video_url = regel.get("video_url") if z.blijvende_media else None
            if not video_url:
                video_url = z.upload(map_ / "klaar" / f"{p['id']}.mp4")
                if z.blijvende_media:
                    regel["video_url"] = video_url
                    schrijf_json(boek_pad, boek)
            # Een tijd die intussen voorbij is, zet de koppeling meteen online: dan liever stoppen
            if datetime.fromisoformat(regel["tijd"]) - datetime.now(timezone.utc) < z.min_vooruit:
                raise PlanFout(verouderd.format(f"de tijd van reel {p['id']} is voorbij terwijl er geüpload werd ({klaar} ingepland)"))
            status, post = z.plan_post(
                account_id=regel["account"], video_url=video_url, caption=p["caption"],
                tijd=regel["tijd"], tijdzone=v["tijdzone"], trial=regel["soort"] == "trial",
                doorzetten=v["doorzetten"], sleutel=regel["sleutel"])
            neem_over(regel, post)
            ig = instagram_deel(post)
            if status == 207 or post.get("status") == "failed" or ig.get("status") == "failed":
                regel["fout"] = ig.get("errorMessage") or "Instagram weigerde hem."
                schrijf_json(boek_pad, boek)
                mislukt.append(f"{p['id']}: {regel['fout']}")
                print(f"MISLUKT: {p['id']} op @{regel['gebruikersnaam']}")
                continue
            schrijf_json(boek_pad, boek)
            klaar += 1
            print(f"ingepland: {p['id']} op @{regel['gebruikersnaam']}" + (" (stond meteen online)" if post.get("status") == "published" else ""))
    print(f"Klaar: {klaar} reels ingepland. {z.naam} zet ze op de tijden uit het voorstel online.")
    if mislukt:
        print("Mislukt:\n" + "\n".join(f"{n}. {m}" for n, m in enumerate(mislukt, 1)))


def stand(map_, ronde, cfg, z):
    boek_pad = Path(map_) / "ingepland.json"
    boek = lees_json(boek_pad, {"posts": {}})
    if zoek_verweesd(z, boek):
        schrijf_json(boek_pad, boek)
    if not boek["posts"]:
        raise PlanFout("Van deze ronde is nog niets ingepland.")
    tz = ZoneInfo(cfg["posten"]["tijdzone"])
    bron = {p["id"]: p for p in ronde["posts"]}
    tel, meldingen = {}, []
    for pid, regel in sorted(boek["posts"].items(), key=lambda kv: kv[1].get("tijd", "")):
        if not regel.get("zernio_id"):
            if regel.get("sleutel"):
                tel["half ingepland (draai --echt opnieuw)"] = tel.get("half ingepland (draai --echt opnieuw)", 0) + 1
            elif regel.get("eerder"):
                tel["gestopt of mislukt, nog niet opnieuw ingepland"] = tel.get("gestopt of mislukt, nog niet opnieuw ingepland", 0) + 1
            continue
        if koppeling_van(regel) != z.naam:
            w = f"via {koppeling_van(regel)} (andere koppeling, hier niet na te kijken)"
            tel[w] = tel.get(w, 0) + 1
            continue
        try:
            post = z.post(regel["zernio_id"], regel.get("account"))
        except KoppelFout as e:
            if e.status != 404:
                tel["niet op te halen"] = tel.get("niet op te halen", 0) + 1
                meldingen.append(f"{pid}: de stand kon nu niet opgehaald worden ({e}).")
                continue
            regel["status"] = "weg"
            tel[f"niet meer bij {z.naam} (gestopt)"] = tel.get(f"niet meer bij {z.naam} (gestopt)", 0) + 1
            meldingen.append(f"{pid} staat niet meer bij {z.naam}. Een nieuw voorstel neemt hem opnieuw mee; wil de gebruiker hem "
                             f"niet meer, haal hem dan uit ronde.json.")
            continue
        ig = instagram_deel(post)
        status = ig.get("status") or post.get("status")
        regel["status"] = status
        if ig.get("platformPostUrl"):
            regel["url"] = ig["platformPostUrl"]
        woord = {"published": "online", "failed": "mislukt", "cancelled": "geannuleerd"}.get(status, "gepland")
        tijd = nl(tijd_van(regel["tijd"]).astimezone(tz))
        if regel.get("fout") and woord == "gepland":
            # Bij het inplannen al fout gegaan (bijvoorbeeld: de video kwam niet aan); hij staat nog wel bij de koppeling
            woord = "mislukt bij het inplannen"
            meldingen.append(f"{pid} op @{regel['gebruikersnaam']} ({tijd}): {regel['fout']}")
        elif woord == "mislukt":
            meldingen.append(f"{pid} op @{regel['gebruikersnaam']} ({tijd}) is mislukt: {ig.get('errorMessage') or 'geen reden gegeven'}. "
                             f"Een nieuw voorstel neemt hem opnieuw mee.")
        tel[woord] = tel.get(woord, 0) + 1
        b = bron.get(pid)
        if b and regel.get("reel") and woord == "gepland" and vingerafdruk(b, cfg) != regel["reel"]:
            meldingen.append(f"{pid} is opnieuw gemaakt nadat hij was ingepland; bij {z.naam} staat nog de oude versie ({tijd}). "
                             f"Wil de gebruiker de nieuwe, dan stopt hij de oude in {z.naam} en plant je de ronde opnieuw in.")
    schrijf_json(boek_pad, boek)
    print("Stand: " + ", ".join(f"{n} {w}" for w, n in tel.items()) + ".")
    if meldingen:
        print("\n".join(f"{n}. {m}" for n, m in enumerate(meldingen, 1)))


def stop_netjes():
    """Een harde stop (SIGTERM, bijvoorbeeld een tijdgrens) ruimt op zoals Ctrl-C: de tunnel gaat dicht en het slot eraf."""
    signal.signal(signal.SIGTERM, lambda *_: sys.exit("Gestopt voordat het klaar was. Draai hetzelfde commando opnieuw; "
                                                       "wat klaar was, blijft klaar."))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ronde")
    ap.add_argument("--echt", action="store_true", help="het voorstel echt klaarzetten via de koppeling")
    ap.add_argument("--stand", action="store_true", help="hoe staan de reels van deze ronde ervoor")
    ap.add_argument("--soort", choices=["auto", "trial", "gewoon"], default="auto")
    ap.add_argument("--vanaf", type=date.fromisoformat, help="niet eerder beginnen dan deze dag (JJJJ-MM-DD)")
    a = ap.parse_args()
    stop_netjes()
    map_ = Path(a.ronde).expanduser().resolve()
    try:
        cfg = laad()
        ronde = lees_ronde(map_, bron=False)
        z = maak_koppeling(cfg)
        with slot(map_, "inplannen"):
            if a.stand:
                stand(map_, ronde, cfg, z)
            elif a.echt:
                echt(map_, ronde, cfg, z)
            else:
                v = voorstel(map_, ronde, cfg, z, a.soort, a.vanaf)
                schrijf_json(map_ / "voorstel.json", v)
                toon_voorstel(v, ronde, lees_json(map_ / "ingepland.json", {"posts": {}}))
    except (PlanFout, RondeFout, InstellingFout, KoppelFout, SlotFout) as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
