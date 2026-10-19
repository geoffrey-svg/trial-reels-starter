#!/usr/bin/env python3
"""
De koppeling met Metricool: reels inplannen als trial reel en de cijfers ophalen, voor wie
Metricool al gebruikt. Geeft alles terug in dezelfde vorm als de Zernio-koppeling, zodat
inplannen en cijfers voor beide hetzelfde werken.

Wat hier staat, is gemeten op echte Metricool-accounts (de content-planner van dit bedrijf,
augustus en september 2026), niet geraden:

1. Elk verzoek draagt de kop X-Mc-Auth met de userToken, plus userId en blogId (het merk) als
   parameter. De API zit in het Advanced-abonnement en hoger (metricool.com/pricing).
2. Inplannen: POST /v2/scheduler/posts met publicationDate {dateTime, timezone} en
   instagramData.type TRIAL_REEL (of REEL); shareTrialAutomatically is "automatisch doorzetten".
3. Metricool neemt een video alleen aan via een openbaar adres. Met saveExternalMediaFiles
   kopieert hij hem naar static.metricool.com terwijl de post gemaakt wordt; daarna mag het
   adres weer dicht. Een lokale video zet media() daarom even openbaar met één cloudflared-tunnel
   voor de hele map (een tunnel per video liep na ongeveer 20 vast op de grens van trycloudflare).
4. Een post heeft per netwerk een status: PENDING, PUBLISHED of ERROR, en na publiceren een publicUrl.
5. Cijfers per reel: /stats/instagram/reels, te koppelen op de code in de url van de reel.
   Metricool loopt daarmee ruim een dag achter.
6. Metricool kent geen sleutel tegen dubbel inplannen. Een post waarvan het antwoord wegviel,
   wordt teruggevonden op account, tijd en caption.

De userToken staat in ~/.config/trial-reels-starter/metricool-token (zet hem daar met
sleutel.py --metricool), nooit in dit project.
"""

import contextlib
import http.server
import json
import os
import re
import shutil
import socket
import subprocess
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
    try:
        basis, eind = None, time.time() + wacht
        while time.time() < eind and basis is None:
            regel = tunnel.stdout.readline()
            if not regel:
                break
            m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", regel)
            if m:
                basis = m.group(0)
        if not basis:
            raise KoppelFout(f"Geen tunnel gekregen binnen {wacht} seconden. Probeer het over een paar minuten opnieuw.", tijdelijk=True)
        threading.Thread(target=lambda: [r for r in tunnel.stdout], daemon=True).start()
        time.sleep(15)   # de trycloudflare-naam staat pas na een paar seconden in DNS (gemeten 27 aug 2026)
        yield basis
    finally:
        tunnel.terminate()
        try:
            tunnel.wait(timeout=10)
        except subprocess.TimeoutExpired:
            tunnel.kill()


@contextlib.contextmanager
def lokale_tunnel(poort):
    yield f"http://127.0.0.1:{poort}"


class Metricool:
    naam = "Metricool"
    marge_minuten = 60                       # altijd minstens een uur vooruit inplannen in Metricool
    min_vooruit_voorstel = timedelta(minutes=30)
    min_vooruit = timedelta(minutes=15)
    blijvende_media = False                  # het tunneladres verloopt; bij een nieuwe poging een nieuw adres

    def __init__(self, user_id, tijdzone, token=None, basis=None, pauze=0.5, slaap=time.sleep, tunnel=cloudflared_tunnel):
        if not str(user_id or "").isdigit():
            raise KoppelFout("Het Metricool-gebruikersnummer (userId) ontbreekt of klopt niet. Zet het met sleutel.py --metricool --user <userId>.")
        self.user = str(user_id)
        self.tz = ZoneInfo(tijdzone)
        self.token = token or lees_token()
        self.basis = (basis or BASIS).rstrip("/")
        self.pauze, self.slaap, self._laatst = pauze, slaap, 0.0
        # TRS_METRICOOL_TUNNEL=lokaal alleen voor proeven tegen een nagemaakte Metricool op deze Mac
        self.tunnel, self._media = (lokale_tunnel if os.environ.get("TRS_METRICOOL_TUNNEL") == "lokaal" else tunnel), None

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
                # Lezen mag opnieuw; een nieuwe post niet (geen sleutel tegen dubbel): die zoekt plan_ronde eerst terug
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
    def _lijst(d):
        d = d.get("data", d) if isinstance(d, dict) else d
        return d if isinstance(d, list) else []

    # Accounts

    def accounts(self):
        """De merken met een Instagram-account erin. In Metricool is een merk (blogId) het account waarop je post."""
        _, d = self.roep("GET", "/admin/simpleProfiles")
        uit = []
        for merk in self._lijst(d):
            blog = merk.get("id") or merk.get("blogId")
            ig = merk.get("instagram") or merk.get("instagramUsername") or (merk.get("networks") or {}).get("instagram")
            if isinstance(ig, dict):
                ig = ig.get("username") or ig.get("name")
            if not blog or not ig:
                continue
            uit.append({"id": str(blog), "gebruikersnaam": str(ig).lstrip("@"), "volgers": self._volgers(blog),
                        "profiel": merk.get("label") or merk.get("name"), "gezond": True})
        return uit

    def _volgers(self, blog):
        """Het laatste aantal volgers uit de tijdlijn van Metricool; None als Metricool het niet geeft."""
        nu = datetime.now(self.tz).replace(microsecond=0, tzinfo=None)
        try:
            _, d = self.roep("GET", "/v2/analytics/timelines", {"blogId": blog, "network": "instagram", "metric": "followers",
                                                                "subject": "account", "from": (nu - timedelta(days=7)).isoformat(),
                                                                "to": nu.isoformat()})
            waarden = (self._lijst(d)[0] or {}).get("values") or []
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
        ig = next((p for p in post.get("providers") or [] if p.get("network") == "instagram"), {})
        status = STATUS.get(str(ig.get("status") or "PENDING").upper(), "scheduled")
        tijd = self._tijd(post)
        return {
            "_id": str(post.get("id")), "status": status, "text": post.get("text") or "", "media": post.get("media") or [],
            "draft": bool(post.get("draft")), "scheduledFor": tijd.isoformat() if tijd else None,
            "platforms": [{"platform": "instagram", "accountId": {"_id": str(blog)},
                           "status": "pending" if status == "scheduled" else status,
                           "errorMessage": ig.get("detailedStatus") or ig.get("errorMessage") or ig.get("error"),
                           "platformPostUrl": ig.get("publicUrl"),
                           "isTrialReel": (post.get("instagramData") or {}).get("type") == "TRIAL_REEL"}],
        }

    def _planning(self, blog, van, tot):
        """Alle posts van een merk tussen twee tijden, in blokken van 20 dagen zodat geen antwoord afgekapt raakt."""
        uit, d = [], van
        while d < tot:
            e = min(d + timedelta(days=20), tot)
            _, res = self.roep("GET", "/v2/scheduler/posts", {"blogId": blog, "start": d.astimezone(self.tz).strftime("%Y-%m-%dT%H:%M:%S"),
                                                              "end": e.astimezone(self.tz).strftime("%Y-%m-%dT%H:%M:%S")})
            uit += [self._vorm(p, blog) for p in self._lijst(res)]
            d = e
        return list({p["_id"]: p for p in uit}.values())

    def bezet(self, account_id):
        nu = datetime.now(timezone.utc)
        return [(p["_id"], datetime.fromisoformat(p["scheduledFor"])) for p in self._planning(account_id, nu - timedelta(days=2), nu + timedelta(days=120))
                if p["scheduledFor"] and not p["draft"] and p["status"] in ("scheduled", "published")]

    def zoek(self, regel):
        """Een post van een eerdere poging: zelfde account, zelfde minuut, zelfde caption."""
        if not regel.get("tijd") or not regel.get("account"):
            return []
        t = datetime.fromisoformat(regel["tijd"])
        return [p for p in self._planning(regel["account"], t - timedelta(minutes=2), t + timedelta(minutes=2))
                if p["scheduledFor"] and abs(datetime.fromisoformat(p["scheduledFor"]) - t) < timedelta(minutes=1)
                and p["text"] == regel.get("caption", "")]

    def post(self, post_id, account=None):
        _, d = self.roep("GET", f"/v2/scheduler/posts/{urllib.parse.quote(str(post_id))}", {"blogId": account})
        return self._vorm(d.get("data", d) if isinstance(d, dict) else {}, account)

    # Video's

    @contextlib.contextmanager
    def media(self, map_):
        """Zet de map met reels even openbaar (één tunnel voor de hele ronde), zodat Metricool de video's kan ophalen."""
        map_ = Path(map_).resolve()

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *a, **kw):
                super().__init__(*a, directory=str(map_), **kw)

            def log_message(self, *a):
                pass

        poort = _vrije_poort()
        server = http.server.ThreadingHTTPServer(("127.0.0.1", poort), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with self.tunnel(poort) as basis:
                self._media = (map_, basis.rstrip("/"))
                yield
        finally:
            self._media = None
            server.shutdown()
            server.server_close()

    def upload(self, bestand):
        if not self._media:
            raise KoppelFout("Er staat geen tunnel open voor de video's.")
        map_, basis = self._media
        return f"{basis}/{urllib.parse.quote(Path(bestand).resolve().relative_to(map_).as_posix())}"

    def plan_post(self, *, account_id, video_url, caption, tijd, tijdzone, trial, doorzetten, sleutel):
        """Plant één reel in. Daarna wordt de post teruggehaald: staat de video niet bij Metricool, dan telt hij als mislukt."""
        lokaal = datetime.fromisoformat(tijd).astimezone(ZoneInfo(tijdzone))
        body = {
            "publicationDate": {"dateTime": lokaal.strftime("%Y-%m-%dT%H:%M:%S"), "timezone": tijdzone},
            "text": caption, "media": [video_url], "autoPublish": True, "saveExternalMediaFiles": True,
            "shortener": False, "draft": False, "providers": [{"network": "instagram"}],
            "instagramData": ({"autoPublish": True, "type": "TRIAL_REEL", "isAiGenerated": False,
                               "shareTrialAutomatically": doorzetten == "automatisch"} if trial
                              else {"autoPublish": True, "type": "REEL", "showReelOnFeed": True}),
        }
        _, d = self.roep("POST", "/v2/scheduler/posts", {"blogId": account_id}, body, pogingen=1)
        nieuw = d.get("data", d) if isinstance(d, dict) else {}
        if not nieuw.get("id"):
            raise KoppelFout(f"Metricool gaf geen post terug: {json.dumps(d)[:200]}")
        post = self.post(nieuw["id"], account_id)
        if not any("static.metricool.com" in str(m) for m in post["media"]):
            # De video kwam niet aan: deze post zou op het geplande moment mislukken
            post["status"] = "failed"
            post["platforms"][0].update(status="failed", errorMessage="De video kwam niet aan bij Metricool. Stop deze post in Metricool en plan opnieuw in.")
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
            if p["status"] == "published" and reel_code(url):
                geplaatst[reel_code(url)] = p
        stats, d = {}, van
        while d < nu:
            e = min(d + timedelta(days=30), nu)
            try:
                _, res = self.roep("GET", "/stats/instagram/reels", {"blogId": account_id, "start": d.strftime("%Y%m%d"), "end": e.strftime("%Y%m%d")})
            except KoppelFout as f:
                raise KoppelFout(f"Metricool gaf geen cijfers voor dit merk ({f.status}). Kijk in Metricool of de cijfers daar wel staan.", status=f.status)
            for r in self._lijst(res):
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
