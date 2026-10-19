#!/usr/bin/env python3
"""
De koppeling met Metricool: reels inplannen als trial reel en de cijfers ophalen, voor wie
Metricool al gebruikt. Geeft alles terug in dezelfde vorm als de Zernio-koppeling, zodat
inplannen en cijfers voor beide hetzelfde werken.

Wat hier staat, is gemeten op echte Metricool-accounts (de content-planner en de inplanscripts
van dit bedrijf, augustus en september 2026, samen ruim 550 trial reels), niet geraden:

1. Elk verzoek draagt de kop X-Mc-Auth met de userToken, plus userId en blogId (het merk) als
   parameter. De API zit in het Advanced-abonnement en hoger (metricool.com/pricing).
2. Inplannen: POST /v2/scheduler/posts met publicationDate {dateTime, timezone} en
   instagramData.type TRIAL_REEL (of REEL); shareTrialAutomatically is "automatisch doorzetten".
3. Metricool neemt een video alleen aan via een openbaar adres. Met saveExternalMediaFiles
   kopieert hij hem naar static.metricool.com terwijl de post gemaakt wordt; daarna mag het
   adres weer dicht. media() zet daarom alleen de reels van deze ronde even openbaar, met één
   cloudflared-tunnel (een tunnel per video liep na ongeveer 20 vast op de grens van trycloudflare).
   Na het openen 90 seconden wachten: met 15 seconden gaf Metricool een kale 404 en maakte hij
   niets aan (gemeten 17 sep 2026). Komt er toch een 404, dan eerst kijken of de post er staat.
4. GET /v2/scheduler/posts leest start en end in de tijdzone van het MERK, niet in de onze. Daarom
   vragen we altijd een dag ruimer en filteren we zelf op het echte moment (dateTime plus timezone
   van de post zelf).
5. Een post heeft per netwerk een status: PENDING, PUBLISHED of ERROR, en na publiceren een publicUrl.
   Een merk kan ook andere netwerken bevatten; alleen het Instagram-deel telt hier.
6. Hetzelfde Instagram-account kan onder twee merken hangen. Wat er gepland staat, telt daarom over
   alle merken met dat account.
7. Cijfers per reel: /stats/instagram/reels, te koppelen op de code in de url van de reel.
   Metricool loopt daarmee ruim een dag achter; voor sommige merken geeft analytics altijd een 500.
8. Metricool kent geen sleutel tegen dubbel inplannen. Een post waarvan het antwoord wegviel,
   wordt teruggevonden op Instagram-account, minuut en caption.

De userToken staat in ~/.config/trial-reels-starter/metricool-token (zet hem daar met
sleutel.py --metricool), nooit in dit project.
"""

import contextlib
import http.server
import json
import os
import queue
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from koppelfout import KoppelFout

BASIS = os.environ.get("TRS_METRICOOL_BASIS", "https://app.metricool.com/api")
TOKENBESTAND = Path.home() / ".config" / "trial-reels-starter" / "metricool-token"
STATUS = {"PENDING": "scheduled", "PUBLISHED": "published", "ERROR": "failed"}
TUNNEL_WACHT = 90              # seconden na het openen van de tunnel (gemeten 17 sep 2026, zie boven)
# Een openbaar trycloudflare-adres; api.trycloudflare.com staat in de foutmelding van cloudflared en is er geen
TUNNEL_RE = re.compile(r"https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com")
NAAM_RE = re.compile(r"@?[A-Za-z0-9_.]{1,30}")


def lees_token():
    token = TOKENBESTAND.read_text(encoding="utf-8").strip() if TOKENBESTAND.exists() else ""
    token = token or os.environ.get("TRS_METRICOOL_TOKEN", "").strip()
    if not token:
        raise KoppelFout("Er is nog geen Metricool-token. Bewaar hem eerst met: python3 engine/scripts/sleutel.py --metricool --user <userId>")
    return token


def reel_code(url):
    m = re.search(r"instagram\.com/(?:[\w.]+/)?(?:reels?|p|tv)/([\w-]+)", url or "")
    return m.group(1) if m else ""


def _vrije_poort():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.contextmanager
def cloudflared_tunnel(poort, wacht=60):
    """Een tijdelijke openbare tunnel naar een lokale poort (cloudflared, zonder account). Geeft het openbare adres."""
    if not shutil.which("cloudflared"):
        raise KoppelFout("Voor Metricool moet een video even openbaar staan, en daarvoor is cloudflared nodig. "
                         "Installeer het met: brew install cloudflared (of ./install.sh --metricool).")
    tunnel = subprocess.Popen(["cloudflared", "tunnel", "--url", f"http://127.0.0.1:{poort}", "--no-autoupdate"],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    # Lezen in een eigen draad: zo geldt de wachttijd ook als cloudflared niets schrijft
    regels = queue.Queue()
    lezer = threading.Thread(target=lambda: [regels.put(r) for r in tunnel.stdout], daemon=True)
    lezer.start()
    try:
        basis, eind = None, time.monotonic() + wacht
        while basis is None and time.monotonic() < eind:
            try:
                m = TUNNEL_RE.search(regels.get(timeout=max(0.1, eind - time.monotonic())))
            except queue.Empty:
                break
            basis = m.group(0) if m else None
        if not basis:
            raise KoppelFout(f"Geen tunnel gekregen binnen {wacht} seconden. Probeer het over een paar minuten opnieuw.", tijdelijk=True)
        yield basis
    finally:
        tunnel.terminate()
        try:
            tunnel.wait(timeout=10)
        except subprocess.TimeoutExpired:
            tunnel.kill()
        lezer.join(timeout=2)
        tunnel.stdout.close()


@contextlib.contextmanager
def lokale_tunnel(poort):
    """Alleen voor proeven tegen een nagemaakte Metricool op deze Mac (TRS_METRICOOL_TUNNEL=lokaal)."""
    yield f"http://127.0.0.1:{poort}"


class Metricool:
    naam = "Metricool"
    marge_minuten = 60                       # altijd minstens een uur vooruit inplannen in Metricool
    min_vooruit_voorstel = timedelta(minutes=30)
    min_vooruit = timedelta(minutes=15)
    blijvende_media = False                  # het tunneladres verloopt; bij een nieuwe poging een nieuw adres

    def __init__(self, user_id, tijdzone, token=None, basis=None, pauze=0.5, slaap=time.sleep, tunnel=cloudflared_tunnel,
                 tunnel_wacht=TUNNEL_WACHT):
        if not str(user_id or "").isdigit():
            raise KoppelFout("Het Metricool-gebruikersnummer (userId) ontbreekt of klopt niet. Zet het met sleutel.py --metricool --user <userId>.")
        self.user = str(user_id)
        self.tz = ZoneInfo(tijdzone)
        self.token = token or lees_token()
        self.basis = (basis or BASIS).rstrip("/")
        self.pauze, self.slaap, self._laatst = pauze, slaap, 0.0
        lokaal = os.environ.get("TRS_METRICOOL_TUNNEL") == "lokaal"
        self.tunnel = lokale_tunnel if lokaal else tunnel
        self.tunnel_wacht = 0 if lokaal else tunnel_wacht
        self._media, self._merken = None, None

    def roep(self, methode, pad, params=None, body=None, pogingen=3, timeout=120):
        q = {"userId": self.user, **(params or {})}
        url = f"{self.basis}{pad}?{urllib.parse.urlencode(q)}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        for poging in range(1, pogingen + 1):
            rust = self.pauze - (time.monotonic() - self._laatst)
            if rust > 0:
                self.slaap(rust)
            self._laatst = time.monotonic()
            verzoek = urllib.request.Request(url, data=data, method=methode, headers={"X-Mc-Auth": self.token, "Accept": "application/json",
                                                                                      **({"Content-Type": "application/json"} if data else {})})
            try:
                with urllib.request.urlopen(verzoek, timeout=timeout) as r:
                    tekst = r.read().decode("utf-8")
                    try:
                        return r.status, json.loads(tekst) if tekst else {}
                    except json.JSONDecodeError:
                        return r.status, {"raw": tekst[:300]}
            except urllib.error.HTTPError as e:
                tekst = e.read().decode("utf-8", "replace")
                # Lezen mag opnieuw; een nieuwe post niet (geen sleutel tegen dubbel): die zoekt plan_post eerst terug
                if (e.code == 429 or e.code >= 500) and poging < pogingen and methode == "GET":
                    self.slaap(min(2.0 * poging, 30))
                    continue
                raise KoppelFout(f"Metricool {methode} {pad}: {e.code} {tekst[:200]}", status=e.code, tijdelijk=e.code == 429 or e.code >= 500)
            except OSError as e:
                if poging < pogingen and methode == "GET":
                    self.slaap(2.0 * poging)
                    continue
                raise KoppelFout(f"Metricool {methode} {pad} gaf geen antwoord ({e}).", tijdelijk=True)
        raise KoppelFout(f"Metricool {methode} {pad}: na {pogingen} pogingen geen antwoord.", tijdelijk=True)

    @staticmethod
    def _lijst(d, wat):
        """De lijst uit een antwoord. Een andere vorm is een fout, nooit stil een lege lijst (dan zou de agenda leeg lijken)."""
        if isinstance(d, dict) and "data" in d:
            d = d["data"]
        if not isinstance(d, list):
            raise KoppelFout(f"Metricool gaf de {wat} in een vorm die de starter niet kent. Probeer het later opnieuw.")
        return d

    # Accounts

    def _merken_met_instagram(self):
        """(blogId, Instagram-naam of None, merk) voor elk merk met een Instagram-account erin."""
        if self._merken is None:
            _, d = self.roep("GET", "/admin/simpleProfiles")
            self._merken = []
            for merk in self._lijst(d, "merken"):
                blog = merk.get("id") or merk.get("blogId")
                ig = merk.get("instagram") or merk.get("instagramUsername") or (merk.get("networks") or {}).get("instagram")
                if isinstance(ig, dict):
                    ig = ig.get("username") or ig.get("name")
                if not blog or not ig:
                    continue
                naam = ig.lstrip("@") if isinstance(ig, str) and NAAM_RE.fullmatch(ig) else None
                self._merken.append((str(blog), naam, merk))
        return self._merken

    def accounts(self):
        """De merken met een Instagram-account erin. In Metricool is een merk (blogId) het account waarop je post.
        Staat hetzelfde Instagram-account onder twee merken, dan staan ze er allebei, met hun merknaam."""
        return [{"id": blog, "gebruikersnaam": naam or f"merk-{blog}", "volgers": self._volgers(blog),
                 "profiel": merk.get("label") or merk.get("name"), "gezond": True}
                for blog, naam, merk in self._merken_met_instagram()]

    def _zelfde_instagram(self, blog):
        """Alle merken met hetzelfde Instagram-account als dit merk (dat komt voor bij Metricool)."""
        lijst = self._merken_met_instagram()
        naam = next((n for b, n, _ in lijst if b == str(blog)), None)
        return [b for b, n, _ in lijst if n and n.lower() == naam.lower()] if naam else [str(blog)]

    def _volgers(self, blog):
        """Het laatste aantal volgers uit de tijdlijn van Metricool; None als Metricool het niet geeft."""
        nu = datetime.now(self.tz).replace(microsecond=0, tzinfo=None)
        try:
            _, d = self.roep("GET", "/v2/analytics/timelines", {"blogId": blog, "network": "instagram", "metric": "followers",
                                                                "subject": "account", "from": (nu - timedelta(days=7)).isoformat(),
                                                                "to": nu.isoformat()})
            waarden = (self._lijst(d, "volgers")[0] or {}).get("values") or []
            laatste = sorted(waarden, key=lambda v: v.get("dateTime", ""))[-1]["value"]
            return int(laatste) if laatste is not None else None
        except (KoppelFout, IndexError, KeyError, TypeError, ValueError, AttributeError):
            return None

    # Posts

    def _tijd(self, post):
        d = post.get("publicationDate") or {}
        if not d.get("dateTime"):
            return None
        t = datetime.fromisoformat(d["dateTime"])
        return (t if t.tzinfo else t.replace(tzinfo=ZoneInfo(d.get("timezone") or self.tz.key))).astimezone(timezone.utc)

    def _vorm(self, post, blog):
        """Een post van Metricool in de vorm van een Zernio-post: _id, status, scheduledFor en het Instagram-deel."""
        ig = next((p for p in post.get("providers") or [] if p.get("network") == "instagram"), None)
        status = "cancelled" if post.get("deleted") else STATUS.get(str((ig or {}).get("status") or "PENDING").upper(), "scheduled")
        tijd = self._tijd(post)
        return {
            "_id": str(post.get("id")), "status": status, "text": post.get("text") or "", "media": post.get("media") or [],
            "draft": bool(post.get("draft")), "scheduledFor": tijd.isoformat() if tijd else None, "instagram": ig is not None,
            "platforms": [{"platform": "instagram", "accountId": {"_id": str(blog)},
                           "status": "pending" if status == "scheduled" else status,
                           "errorMessage": (ig or {}).get("detailedStatus") or (ig or {}).get("errorMessage") or (ig or {}).get("error"),
                           "platformPostUrl": (ig or {}).get("publicUrl"),
                           "isTrialReel": (post.get("instagramData") or {}).get("type") == "TRIAL_REEL"}],
        }

    def _planning(self, blog, van, tot):
        """Alle posts van een merk tussen twee momenten. Metricool leest het venster in de tijdzone van het merk, dus we
        vragen een dag ruimer (in blokken van 20 dagen, zodat geen antwoord afgekapt raakt) en filteren zelf."""
        uit, d, eind = {}, van - timedelta(days=1), tot + timedelta(days=1)
        while d < eind:
            e = min(d + timedelta(days=20), eind)
            _, res = self.roep("GET", "/v2/scheduler/posts", {"blogId": blog, "start": d.astimezone(self.tz).strftime("%Y-%m-%dT%H:%M:%S"),
                                                              "end": e.astimezone(self.tz).strftime("%Y-%m-%dT%H:%M:%S")})
            for p in self._lijst(res, "geplande posts"):
                v = self._vorm(p, blog)
                if v["scheduledFor"] and van <= datetime.fromisoformat(v["scheduledFor"]) < tot:
                    uit[v["_id"]] = v
            d = e
        return list(uit.values())

    def bezet(self, account_id):
        """Wat er op dit Instagram-account gepland staat of net gepost is, over alle merken met dat account. Alleen
        Instagram telt: een LinkedIn- of Facebook-post in hetzelfde merk niet."""
        nu = datetime.now(timezone.utc)
        uit = {}
        for blog in self._zelfde_instagram(account_id):
            for p in self._planning(blog, nu - timedelta(days=2), nu + timedelta(days=120)):
                if p["instagram"] and not p["draft"] and p["status"] in ("scheduled", "published"):
                    uit[p["_id"]] = datetime.fromisoformat(p["scheduledFor"])
        return list(uit.items())

    def _vind(self, account_id, tijd, caption):
        """Instagram-posts op deze minuut met deze caption, op elk merk met hetzelfde Instagram-account."""
        t = datetime.fromisoformat(tijd).astimezone(timezone.utc)
        gevonden = []
        for blog in self._zelfde_instagram(account_id):
            gevonden += [p for p in self._planning(blog, t - timedelta(minutes=2), t + timedelta(minutes=2))
                         if p["instagram"] and not p["draft"] and p["status"] != "cancelled"
                         and abs(datetime.fromisoformat(p["scheduledFor"]) - t) < timedelta(minutes=1)
                         and p["text"].strip() == (caption or "").strip()]
        return gevonden

    def zoek(self, regel):
        """Een post van een eerdere poging: zelfde Instagram-account, zelfde minuut, zelfde caption."""
        if not regel.get("tijd") or not regel.get("account"):
            return []
        return self._vind(regel["account"], regel["tijd"], regel.get("caption", ""))

    def post(self, post_id, account=None):
        _, d = self.roep("GET", f"/v2/scheduler/posts/{urllib.parse.quote(str(post_id))}", {"blogId": account})
        p = d.get("data", d) if isinstance(d, dict) else None
        if not isinstance(p, dict) or not p.get("id"):
            raise KoppelFout(f"Metricool gaf post {post_id} niet terug in een bekende vorm.")
        return self._vorm(p, account)

    # Video's

    @contextlib.contextmanager
    def media(self, bestanden):
        """Zet alleen deze reels even openbaar (één tunnel voor de hele ronde), zodat Metricool ze kan ophalen, en kijkt of
        dat werkt voordat er iets wordt ingepland."""
        bestanden = [Path(b).resolve() for b in bestanden]
        with tempfile.TemporaryDirectory(prefix="trs-media-") as map_:
            for b in bestanden:
                (Path(map_) / b.name).symlink_to(b)

            class Handler(http.server.SimpleHTTPRequestHandler):
                def __init__(self, *a, **kw):
                    super().__init__(*a, directory=map_, **kw)

                def list_directory(self, path):          # geen lijst van wat er staat
                    self.send_error(404)

                def log_message(self, *a):
                    pass

            poort = _vrije_poort()
            server = http.server.ThreadingHTTPServer(("127.0.0.1", poort), Handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                with self.tunnel(poort) as basis:
                    self.slaap(self.tunnel_wacht)      # eerder geeft Metricool een kale 404 (gemeten 17 sep 2026)
                    self._media = basis.rstrip("/")
                    if bestanden:
                        self._probeer(bestanden[0])
                    yield
            finally:
                self._media = None
                server.shutdown()
                server.server_close()

    def _probeer(self, bestand):
        """Kijk of de eerste video via de tunnel echt op te halen is, met de goede grootte."""
        url = self.upload(bestand)
        for poging in range(1, 6):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=20) as r:
                    if r.status == 200 and int(r.headers.get("Content-Length") or -1) == bestand.stat().st_size:
                        return
            except (OSError, ValueError):
                pass
            if poging < 5:
                self.slaap(5.0 * poging)
        raise KoppelFout("De video's zijn via de tunnel niet bereikbaar, dus Metricool kan ze niet ophalen. Er is niets ingepland. "
                         "Probeer het over een paar minuten opnieuw.", tijdelijk=True)

    def upload(self, bestand):
        if not self._media:
            raise KoppelFout("Er staat geen tunnel open voor de video's.")
        return f"{self._media}/{urllib.parse.quote(Path(bestand).name)}"

    def plan_post(self, *, account_id, video_url, caption, tijd, tijdzone, trial, doorzetten, sleutel):
        """Plant één reel in en haalt hem daarna terug: staat de video niet bij Metricool, of bewaarde Metricool een andere
        tijd, soort of caption, dan telt hij als mislukt (de post blijft in Metricool staan tot de gebruiker hem stopt)."""
        lokaal = datetime.fromisoformat(tijd).astimezone(ZoneInfo(tijdzone))
        body = {
            "publicationDate": {"dateTime": lokaal.strftime("%Y-%m-%dT%H:%M:%S"), "timezone": tijdzone},
            "text": caption, "media": [video_url], "autoPublish": True, "saveExternalMediaFiles": True,
            "shortener": False, "draft": False, "providers": [{"network": "instagram"}],
            "instagramData": ({"autoPublish": True, "type": "TRIAL_REEL", "isAiGenerated": False,
                               "shareTrialAutomatically": doorzetten == "automatisch"} if trial
                              else {"autoPublish": True, "type": "REEL", "showReelOnFeed": True}),
        }
        nieuw_id = None
        for poging in range(1, 4):
            try:
                _, d = self.roep("POST", "/v2/scheduler/posts", {"blogId": account_id}, body, pogingen=1)
            except KoppelFout as e:
                # Een kale 404 kwam in de metingen terwijl de tunnel nog opstartte: eerst kijken of hij er toch staat
                if e.status != 404 or poging == 3:
                    raise
                self.slaap(30)
                al = self._vind(account_id, tijd, caption)
                if al:
                    nieuw_id = al[0]["_id"]
                    break
                continue
            nieuw = d.get("data", d) if isinstance(d, dict) else {}
            nieuw_id = nieuw.get("id") if isinstance(nieuw, dict) else None
            if not nieuw_id:
                raise KoppelFout(f"Metricool gaf geen post terug: {json.dumps(d)[:200]}")
            break
        post = self.post(nieuw_id, account_id)
        fout = None
        if not any("static.metricool.com" in str(m) for m in post["media"]):
            fout = "De video kwam niet aan bij Metricool."
        elif post["scheduledFor"] is None or abs(datetime.fromisoformat(post["scheduledFor"]) - datetime.fromisoformat(tijd)) >= timedelta(minutes=1):
            fout = "Metricool bewaarde hem op een andere tijd."
        elif post["platforms"][0]["isTrialReel"] != bool(trial):
            fout = "Metricool bewaarde hem als " + ("gewone reel, die ook de volgers zien." if trial else "trial reel.")
        elif post["text"].strip() != (caption or "").strip():
            fout = "Metricool bewaarde een andere caption."
        if fout:
            post["status"] = "failed"
            post["platforms"][0].update(status="failed", errorMessage=f"{fout} Stop deze post in Metricool; een nieuw voorstel "
                                                                      "neemt de reel daarna opnieuw mee.")
            return 207, post
        return 201, post

    # Cijfers

    def cijfers(self, account_id, vanaf):
        """De cijfers van de reels die via Metricool zijn ingepland, in de vorm van de Zernio-analytics."""
        van = datetime.fromisoformat(vanaf).replace(tzinfo=self.tz)
        nu = datetime.now(self.tz)
        geplaatst = {}
        for p in self._planning(account_id, van, nu):
            url = p["platforms"][0].get("platformPostUrl")
            if p["instagram"] and p["status"] == "published" and reel_code(url):
                geplaatst[reel_code(url)] = p
        stats, d, eind = {}, van - timedelta(days=1), nu + timedelta(days=1)
        while d < eind:
            e = min(d + timedelta(days=30), eind)
            try:
                _, res = self.roep("GET", "/stats/instagram/reels", {"blogId": account_id, "start": d.strftime("%Y%m%d"), "end": e.strftime("%Y%m%d")})
            except KoppelFout as f:
                raise KoppelFout(f"Metricool gaf geen cijfers voor dit merk ({f.status}). Kijk in Metricool of de cijfers daar wel staan.", status=f.status)
            for r in self._lijst(res, "cijfers"):
                if reel_code(r.get("url")):
                    stats[reel_code(r["url"])] = r
            d = e
        uit = []
        for code, p in geplaatst.items():
            s = stats.get(code)
            if not s:
                continue   # nog geen cijfers: Metricool loopt ruim een dag achter
            views = next((s.get(k) for k in ("views", "videoViewsTotal", "videoViews") if s.get(k) is not None), None)
            uit.append({"_id": f"mc-{code}", "latePostId": p["_id"], "publishedAt": p["scheduledFor"],
                        "platformPostUrl": p["platforms"][0]["platformPostUrl"],
                        "analytics": {"views": views, "reach": s.get("reach"), "likes": s.get("likes"), "comments": s.get("comments"),
                                      "shares": s.get("shares"), "saves": s.get("saved"), "igReelsAvgWatchTime": s.get("averageWatchTime")}})
        return uit
