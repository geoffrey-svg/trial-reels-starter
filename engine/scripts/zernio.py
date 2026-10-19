#!/usr/bin/env python3
"""
De koppeling met Zernio, de dienst die de reels op Instagram zet en de cijfers ophaalt.

Alles volgt Zernio's eigen beschrijving van de API (zernio.com/openapi.json en
docs.zernio.com, gelezen 19 okt 2026):

1. Een sleutel begint met sk_ en heeft daarna 64 tekens 0-9a-f.
2. Een video gaat eerst naar Zernio met POST /v1/media/presign (geeft uploadUrl en
   publicUrl) en een PUT van het bestand naar uploadUrl.
3. Inplannen: POST /v1/posts met scheduledFor en timezone. Een trial reel krijgt
   platformSpecificData.trialParams.graduationStrategy (MANUAL of SS_PERFORMANCE).
   Met de kop Idempotency-Key geeft een herhaling binnen 24 uur de eerste post terug in
   plaats van een tweede; 409 met code idempotency_conflict betekent: de eerste loopt nog.
4. Het gratis abonnement mag 60 verzoeken per minuut, dus er zit steeds ruim een
   seconde tussen. 429 zegt in Retry-After hoe lang wachten.

De sleutel komt uit ~/.config/trial-reels-starter/zernio-api-key (zet hem daar met sleutel.py),
nooit uit dit project. Een algemene ZERNIO_API_KEY op de Mac (van een ander project) telt niet;
alleen als er geen bestand is, wordt TRS_ZERNIO_API_KEY gebruikt.
"""

import contextlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from koppelfout import KoppelFout

BASIS = os.environ.get("TRS_ZERNIO_BASIS", "https://zernio.com/api/v1")
SLEUTELBESTAND = Path.home() / ".config" / "trial-reels-starter" / "zernio-api-key"
SLEUTEL_RE = re.compile(r"^sk_[0-9a-f]{64}$")
TAG = "trial-reels-starter"


ZernioFout = KoppelFout   # dezelfde fout als bij Metricool, zodat de scripts er één keer op letten


def lees_sleutel():
    sleutel = SLEUTELBESTAND.read_text(encoding="utf-8").strip() if SLEUTELBESTAND.exists() else ""
    sleutel = sleutel or os.environ.get("TRS_ZERNIO_API_KEY", "").strip()
    if not sleutel:
        raise ZernioFout("Er is nog geen Zernio-sleutel. Bewaar hem eerst met: python3 engine/scripts/sleutel.py")
    if not SLEUTEL_RE.match(sleutel):
        raise ZernioFout("De Zernio-sleutel heeft niet de goede vorm (sk_ plus 64 tekens). Maak in Zernio een nieuwe.")
    return sleutel


class Zernio:
    naam = "Zernio"
    marge_minuten = 20                       # zo ver vooruit plant het voorstel op zijn vroegst
    min_vooruit_voorstel = timedelta(minutes=5)   # zo ver vooruit moet elke tijd nog liggen als --echt begint
    min_vooruit = timedelta(minutes=2)       # en zo ver vooruit vlak voor het inplannen van één reel
    blijvende_media = True                   # een geüploade video blijft bij Zernio staan

    def __init__(self, sleutel=None, basis=None, pauze=1.1, slaap=time.sleep):
        self.sleutel = sleutel or lees_sleutel()
        self.basis = (basis or BASIS).rstrip("/")
        self.pauze, self.slaap, self._laatst = pauze, slaap, 0.0

    def _wacht_beurt(self):
        rust = self.pauze - (time.monotonic() - self._laatst)
        if rust > 0:
            self.slaap(rust)
        self._laatst = time.monotonic()

    def roep(self, methode, pad, body=None, kop=None, query=None, pogingen=3, timeout=60):
        """Eén verzoek. Herhaalt alleen wat veilig te herhalen is: lezen, en schrijven met een eigen sleutel."""
        url = self.basis + pad + ("?" + urllib.parse.urlencode(query) if query else "")
        koppen = {"Authorization": f"Bearer {self.sleutel}", "Accept": "application/json", **(kop or {})}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            koppen["Content-Type"] = "application/json"
        for poging in range(1, pogingen + 1):
            self._wacht_beurt()
            try:
                with urllib.request.urlopen(urllib.request.Request(url, data=data, method=methode, headers=koppen),
                                            timeout=timeout) as r:
                    tekst = r.read().decode("utf-8")
                    return r.status, (json.loads(tekst) if tekst else {})
            except urllib.error.HTTPError as e:
                tekst = e.read().decode("utf-8", "replace")
                try:
                    inhoud = json.loads(tekst) if tekst else {}
                except json.JSONDecodeError:
                    inhoud = {"raw": tekst[:300]}
                bezig = e.code == 409 and isinstance(inhoud, dict) and inhoud.get("code") == "idempotency_conflict"
                if (e.code == 429 or e.code >= 500 or bezig) and poging < pogingen:
                    try:
                        wacht = float(e.headers.get("Retry-After") or 0)
                    except ValueError:
                        wacht = 0
                    self.slaap(min(max(wacht, 2.0 * poging), 60))
                    continue
                melding = (inhoud.get("error") or inhoud.get("message")) if isinstance(inhoud, dict) else None
                raise ZernioFout(f"Zernio {methode} {pad}: {e.code} {melding or tekst[:200]}", status=e.code,
                                 data=inhoud, tijdelijk=e.code == 429 or e.code >= 500)
            except OSError as e:   # geen verbinding of time-out (URLError, socket.timeout en ConnectionError zijn alle OSError)
                if poging < pogingen:
                    self.slaap(2.0 * poging)
                    continue
                raise ZernioFout(f"Zernio {methode} {pad} gaf geen antwoord ({e}).", tijdelijk=True)
        raise ZernioFout(f"Zernio {methode} {pad}: na {pogingen} pogingen geen antwoord.", tijdelijk=True)

    # Accounts en koppelen

    def accounts(self):
        """De Instagram-accounts in dit Zernio-account, met volgers als Zernio die kent."""
        _, d = self.roep("GET", "/accounts", query={"platform": "instagram"})
        uit = []
        for a in d.get("accounts") or []:
            profiel = a.get("profileId")
            uit.append({
                "id": a.get("_id"),
                "gebruikersnaam": str(a.get("username") or "").lstrip("@"),
                "volgers": a.get("followersCount") if isinstance(a.get("followersCount"), (int, float)) else None,
                "profiel": profiel.get("_id") if isinstance(profiel, dict) else profiel,
                # enabled false: alleen voor advertenties aangezet, posten weigert Zernio dan met 403
                "gezond": a.get("isActive") is not False and not a.get("needsReconnection") and a.get("enabled") is not False,
            })
        return uit

    def profielen(self):
        _, d = self.roep("GET", "/profiles")
        return d.get("profiles") or []

    def maak_profiel(self, naam):
        _, d = self.roep("POST", "/profiles", body={"name": naam}, pogingen=1)
        return (d.get("profile") or {}).get("_id")

    def koppellink(self, profiel_id):
        _, d = self.roep("GET", "/connect/instagram", query={"profileId": profiel_id})
        if not d.get("authUrl"):
            raise ZernioFout("Zernio gaf geen koppellink terug.")
        return d["authUrl"]

    # Video's

    def media(self, bestanden):
        """Bij Zernio gaat elke video zelf omhoog; er hoeft niets klaar te staan."""
        return contextlib.nullcontext()

    def upload(self, bestand):
        """Zet een video bij Zernio en geeft het openbare adres terug."""
        bestand = Path(bestand)
        _, d = self.roep("POST", "/media/presign",
                         body={"filename": bestand.name, "contentType": "video/mp4", "size": bestand.stat().st_size})
        if not d.get("uploadUrl") or not d.get("publicUrl"):
            raise ZernioFout("Zernio gaf geen uploadadres terug.")
        for poging in range(1, 4):
            try:
                with bestand.open("rb") as f:
                    verzoek = urllib.request.Request(d["uploadUrl"], data=f, method="PUT", headers={
                        "Content-Type": "video/mp4", "Content-Length": str(bestand.stat().st_size)})
                    with urllib.request.urlopen(verzoek, timeout=600) as r:
                        if 200 <= r.status < 300:
                            return d["publicUrl"]
            except OSError as e:
                if poging == 3:
                    raise ZernioFout(f"Uploaden van {bestand.name} lukte niet ({e}).", tijdelijk=True)
                self.slaap(3.0 * poging)
        raise ZernioFout(f"Uploaden van {bestand.name} lukte niet.", tijdelijk=True)

    # Posts

    def plan_post(self, *, account_id, video_url, caption, tijd, tijdzone, trial, doorzetten, sleutel):
        """Plant één reel in. sleutel is vast per post: een herhaling maakt dan nooit een tweede post."""
        instagram = {"trialParams": {"graduationStrategy": "SS_PERFORMANCE" if doorzetten == "automatisch" else "MANUAL"}} if trial else {}
        body = {
            "content": caption,
            "mediaItems": [{"type": "video", "url": video_url}],
            "platforms": [{"platform": "instagram", "accountId": account_id, "platformSpecificData": instagram}],
            "scheduledFor": tijd,
            "timezone": tijdzone,
            "tags": [TAG, f"trs-{sleutel}"],
        }
        status, d = self.roep("POST", "/posts", body=body, kop={"Idempotency-Key": f"trs-{sleutel}"})
        post = d.get("post") or {}
        if not post.get("_id"):
            raise ZernioFout("Zernio gaf geen post terug.")
        # 207: Zernio publiceerde meteen (een tijd in het verleden) en dat mislukte op Instagram
        return status, post

    def posts(self, *, tags=None, account_id=None, status=None, vanaf=None):
        uit, pagina = [], 1
        while True:
            q = {"limit": 100, "page": pagina}
            if tags:
                q["tags"] = ",".join(tags)
            if account_id:
                q["accountId"] = account_id
            if status:
                q["status"] = status
            if vanaf:
                q["fromDate"] = vanaf
            _, d = self.roep("GET", "/posts", query=q)
            lijst = d.get("posts") or []
            uit.extend(lijst)
            pages = (d.get("pagination") or {}).get("pages") or 1
            if pagina >= pages or not lijst or pagina >= 50:
                return uit
            pagina += 1

    def post(self, post_id, account=None):
        _, d = self.roep("GET", f"/posts/{urllib.parse.quote(post_id)}")
        return d.get("post") or d

    def bezet(self, account_id):
        """Wat er op dit account gepland staat of net gepost is: [(post-id, tijd)]. Ook wat de gebruiker zelf in Zernio zette."""
        eergisteren = (datetime.now(timezone.utc) - timedelta(days=2)).date().isoformat()
        posts = self.posts(account_id=account_id, status="scheduled") + self.posts(account_id=account_id, status="publishing") \
            + self.posts(account_id=account_id, status="published", vanaf=eergisteren)
        uit = {}
        for p in posts:
            if p.get("status") in ("scheduled", "publishing", "published", "partial") and p.get("scheduledFor"):
                uit[p["_id"]] = datetime.fromisoformat(p["scheduledFor"].replace("Z", "+00:00"))
        return list(uit.items())

    def zoek(self, regel):
        """Een post die een eerdere poging wel maakte maar waarvan het antwoord wegviel: hij draagt de eigen sleutel als tag."""
        return self.posts(tags=[f"trs-{regel['sleutel']}"])

    def cijfers(self, account_id, vanaf):
        """De cijfers van alle reels die via Zernio op dit account gezet zijn, vanaf een datum (JJJJ-MM-DD)."""
        uit, pagina = [], 1
        while pagina <= 40:
            _, d = self.roep("GET", "/analytics", query={"accountId": account_id, "source": "late", "fromDate": vanaf,
                                                         "limit": 50, "page": pagina})
            lijst = d.get("posts") or []
            uit.extend(lijst)
            if len(lijst) < 50:
                break
            pagina += 1
        return uit


def instagram_deel(post):
    """Het Instagram-deel van een post: status, foutmelding en adres."""
    for p in post.get("platforms") or []:
        if p.get("platform") == "instagram":
            return p
    return {}
