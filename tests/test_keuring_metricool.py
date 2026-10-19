"""
Wat de keuring van de Metricool-koppeling (19 okt 2026) vond, als vaste tests: elke test laat zien dat het
gevonden gedrag nu goed gaat. Metricool, Zernio en cloudflared zijn hier nagemaakt; niets gaat naar buiten.
"""

import contextlib
import io
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from unittest import mock
from zoneinfo import ZoneInfo

import basis
import cijfers
import instellingen as ins
import koppel
import koppeling
import maak_reels as mr
import metricool as mmod
import plan_ronde as pr
from koppelfout import KoppelFout
from metricool import Metricool
from nep_metricool import TOKEN, USER, NepMetricool
from nep_zernio import SLEUTEL, NepZernio
from planning import PlanFout
from zernio import Zernio

AMS = ZoneInfo("Europe/Amsterdam")
SCRIPTS = basis.REPO / "engine" / "scripts"


def cfg(**posten):
    c = ins.keur(json.loads(ins.STANDAARD.read_text(encoding="utf-8")))
    c["posten"].update(posten)
    return c


@contextlib.contextmanager
def lokale_tunnel(poort):
    yield f"http://127.0.0.1:{poort}"


def vervang_route(nep, nieuwe):
    """Laat de nagemaakte Metricool op één punt anders antwoorden: nieuwe(handler, pad, q, body) -> antwoord of None."""
    H = nep.server.RequestHandlerClass

    class H2(H):
        def _route(self, pad, q, body):
            r = nieuwe(self, pad, q, body)
            return r if r is not None else super()._route(pad, q, body)

    nep.server.RequestHandlerClass = H2


def merk_tijdzone(nep, tz):
    """Metricool leest start en end van /v2/scheduler/posts in de tijdzone van het MERK (gemeten in het OS, Eelco
    Dashboard, haalPlannerPosts). Hier staat het merk op een andere tijdzone dan de instellingen."""
    def moment(p):
        d = p["publicationDate"]
        return datetime.fromisoformat(d["dateTime"]).replace(tzinfo=ZoneInfo(d["timezone"]))

    def route(h, pad, q, body):
        if h.command == "GET" and pad == "/v2/scheduler/posts":
            van = datetime.fromisoformat(q["start"]).replace(tzinfo=ZoneInfo(tz))
            tot = datetime.fromisoformat(q["end"]).replace(tzinfo=ZoneInfo(tz))
            return 200, {"data": [p for p in nep.posts.values() if p["_blog"] == q.get("blogId") and van <= moment(p) < tot]}
        return None
    vervang_route(nep, route)


def valt_weg(nep):
    """De volgende POST komt aan maar zijn antwoord niet, en daarna is de agenda drie keer onbereikbaar (terugzoeken lukt
    in die run dus niet)."""
    stand = {"post": False, "fout": 0}

    def route(h, pad, q, body):
        if h.command == "POST" and pad == "/v2/scheduler/posts":
            stand["post"] = True
        elif h.command == "GET" and pad == "/v2/scheduler/posts" and stand["post"] and stand["fout"] < 3:
            stand["fout"] += 1
            return 503, {"message": "storing"}
    vervang_route(nep, route)
    nep.storing = [(r"POST /api/v2/scheduler/posts$", "slik")]


def eigen_post(nep, nr, blog, moment, netwerk="instagram", tekst="Eigen post"):
    nep.posts[str(nr)] = {"id": nr, "_blog": blog, "text": tekst, "media": [], "draft": False,
                          "publicationDate": {"dateTime": moment.astimezone(AMS).strftime("%Y-%m-%dT%H:%M:%S"), "timezone": "Europe/Amsterdam"},
                          "providers": [{"network": n, "status": "PENDING"} for n in (netwerk if isinstance(netwerk, list) else [netwerk])]}


class Basis(unittest.TestCase):
    def setUp(self):
        self.nep = NepMetricool()
        self.nep.merken = [{"id": 111, "label": "Mijn merk", "instagram": "mijn_merk"},
                           {"id": 222, "label": "Klein merk", "instagram": "klein_merk"}]
        self.nep.volgers = {"111": 1500, "222": 1500}
        self.z = self.metricool()
        self.rondes = []
        self.map_ = self.maak_ronde("keuring-ronde")
        ins.MIJN.mkdir(parents=True, exist_ok=True)
        pr.ACCOUNTS.write_text(json.dumps([{"id": "111", "gebruikersnaam": "mijn_merk"}]))

    def tearDown(self):
        self.nep.stop()
        for m in self.rondes:            # alleen de tijdelijke testmap, zodat de volgende test er geen last van heeft
            shutil.rmtree(m, ignore_errors=True)
        koppeling.schrijf({"soort": "zernio"})

    def maak_ronde(self, naam, captions=None):
        map_ = ins.MIJN / "rondes" / naam
        shutil.rmtree(map_, ignore_errors=True)
        (map_ / "klaar").mkdir(parents=True)
        self.rondes.append(map_)
        posts = [{"id": f"0{i}", "video": f"weg/0{i}.mp4", "tekst": f"Tekst {i} {naam}", "caption": c}
                 for i, c in enumerate(captions or [f"Caption {i}" for i in range(1, 4)], 1)]
        for p in posts:
            (map_ / "klaar" / f"{p['id']}.mp4").write_bytes(b"\0" * 2000 + p["id"].encode())
            (map_ / "klaar" / f"{p['id']}.json").write_text(json.dumps(mr.vingerafdruk(p, cfg())))
        (map_ / "ronde.json").write_text(json.dumps({"naam": naam, "posts": posts}))
        return map_

    def metricool(self, tunnel=lokale_tunnel, slaap=lambda s: None):
        return Metricool(user_id=USER, tijdzone="Europe/Amsterdam", token=TOKEN, basis=self.nep.basis, pauze=0,
                         slaap=slaap, tunnel=tunnel)

    def zernio(self, nz):
        nz.accounts = [{"_id": "a" * 24, "platform": "instagram", "profileId": {"_id": "p" * 24}, "username": "mijn_merk",
                        "isActive": True, "followersCount": 1500}]
        return Zernio(sleutel=SLEUTEL, basis=nz.basis, pauze=0, slaap=lambda s: None)

    def voorstel(self, z=None, map_=None):
        map_ = map_ or self.map_
        v = pr.voorstel(map_, mr.lees_ronde(map_, bron=False), cfg(), z or self.z, "auto", None)
        pr.schrijf_json(map_ / "voorstel.json", v)
        return v

    def echt(self, z=None, map_=None):
        map_ = map_ or self.map_
        with redirect_stdout(io.StringIO()) as uit:
            pr.echt(map_, mr.lees_ronde(map_, bron=False), cfg(), z or self.z)
        return uit.getvalue()

    def stand(self, z=None, map_=None):
        map_ = map_ or self.map_
        with redirect_stdout(io.StringIO()) as uit:
            pr.stand(map_, mr.lees_ronde(map_, bron=False), cfg(), z or self.z)
        return uit.getvalue()

    def boek(self, map_=None):
        return json.loads(((map_ or self.map_) / "ingepland.json").read_text())["posts"]

    def tel_caption(self, tekst):
        return sum(1 for p in self.nep.posts.values() if p["text"].strip() == tekst.strip())

    def antwoord_valt_weg(self):
        """--echt maakt reel 01 aan, maar het antwoord van Metricool komt niet terug, en terugzoeken lukt in die run ook niet."""
        valt_weg(self.nep)
        with self.assertRaises(KoppelFout), redirect_stdout(io.StringIO()):
            pr.echt(self.map_, mr.lees_ronde(self.map_, bron=False), cfg(), self.z)


class TestZwaar(Basis):
    def test_z1_weggevallen_antwoord_teruggevonden_bij_andere_tijdzone_van_het_merk(self):
        merk_tijdzone(self.nep, "Europe/London")
        self.voorstel()
        self.antwoord_valt_weg()
        self.assertIn("al bij Metricool: 01", self.echt())
        self.assertEqual(self.tel_caption("Caption 1"), 1)
        self.assertEqual(len(self.nep.posts), 3)

    def test_z1_teruggevonden_als_metricool_de_caption_iets_anders_bewaart(self):
        self.map_ = self.maak_ronde("keuring-caption", ["Caption 1 #reels\n", "Caption 2", "Caption 3"])

        def knip(h, pad, q, body):
            if h.command == "POST" and pad == "/v2/scheduler/posts" and body:
                body["text"] = body.get("text", "").strip()
        vervang_route(self.nep, knip)
        self.voorstel()
        self.antwoord_valt_weg()
        self.echt()
        self.assertEqual(self.tel_caption("Caption 1 #reels"), 1)

    def test_z2_na_de_tunnel_90_seconden_wachten(self):
        gewacht = []
        self.z = self.metricool(slaap=gewacht.append)
        self.voorstel()
        self.echt()
        self.assertIn(90, gewacht, "styleguide 10.8: met 15 seconden gaf Metricool een kale 404")

    def test_z2_een_kale_404_wordt_opnieuw_geprobeerd(self):
        self.voorstel()
        self.nep.storing = [(r"POST /api/v2/scheduler/posts$", 404)]
        self.assertIn("3 reels ingepland", self.echt())
        self.assertEqual(self.tel_caption("Caption 1"), 1)

    def test_z2_een_404_terwijl_de_post_er_toch_kwam_geeft_geen_tweede(self):
        self.voorstel()
        eerste = []

        def toch_gemaakt(h, pad, q, body):
            if h.command == "POST" and pad == "/v2/scheduler/posts" and not eerste:
                eerste.append(1)
                type(h).__mro__[1]._route(h, pad, q, body)     # Metricool maakt hem wel aan...
                return 404, {"message": "Not Found"}            # ...maar antwoordt met een kale 404
        vervang_route(self.nep, toch_gemaakt)
        self.echt()
        self.assertEqual(self.tel_caption("Caption 1"), 1)
        self.assertEqual(len(self.nep.posts), 3)


class TestMiddel(Basis):
    def test_m2_foutregel_van_cloudflared_is_geen_tunneladres(self):
        self.assertIsNone(mmod.TUNNEL_RE.search("failed to request quick Tunnel: Post \"https://api.trycloudflare.com/tunnel\""))
        self.assertEqual(mmod.TUNNEL_RE.search("|  https://rustig-blauw-paard.trycloudflare.com  |").group(0),
                         "https://rustig-blauw-paard.trycloudflare.com")

    def test_m3_andere_tijd_bij_metricool_is_mislukt(self):
        def anders(h, pad, q, body):
            if h.command == "POST" and pad == "/v2/scheduler/posts" and body:
                body["publicationDate"] = {**body["publicationDate"], "timezone": "Europe/London"}
        vervang_route(self.nep, anders)
        self.voorstel()
        uit = self.echt()
        self.assertIn("MISLUKT", uit)
        self.assertIn("andere tijd", uit)
        self.assertIn("0 reels ingepland", uit)

    def test_m3_gewone_reel_in_plaats_van_trial_is_mislukt(self):
        def anders(h, pad, q, body):
            if h.command == "POST" and pad == "/v2/scheduler/posts" and body:
                body["instagramData"] = {**body["instagramData"], "type": "REEL"}
        vervang_route(self.nep, anders)
        self.voorstel()
        uit = self.echt()
        self.assertIn("gewone reel", uit)
        self.assertIn("Stop deze post in Metricool", uit)

    def test_m4_zelfde_instagram_onder_twee_merken(self):
        self.nep.merken = [{"id": 111, "label": "Hoofdmerk", "instagram": "mijn_merk"},
                           {"id": 444, "label": "Tweede merk", "instagram": "mijn_merk"}]
        self.nep.volgers = {"111": 1500, "444": 1500}
        with self.assertRaises(SystemExit) as fout, redirect_stdout(io.StringIO()):
            koppel.gebruik(self.z, ["mijn_merk"])
        self.assertIn("nummer 444", str(fout.exception), "niet stil een merk kiezen")
        with redirect_stdout(io.StringIO()):
            koppel.gebruik(self.z, ["111"])
        self.assertEqual(json.loads(pr.ACCOUNTS.read_text()), [{"id": "111", "gebruikersnaam": "mijn_merk"}])
        v = self.voorstel()
        eigen_post(self.nep, 1, "444", datetime.fromisoformat(v["posts"][0]["tijd"]))   # via het andere merk
        v2 = self.voorstel()
        self.assertNotEqual(v2["posts"][0]["tijd"], v["posts"][0]["tijd"], "de post via het andere merk telt mee")

    def test_m5_andere_netwerken_tellen_niet_mee(self):
        v = self.voorstel()
        start = datetime.now(AMS).replace(hour=9, minute=0, second=0, microsecond=0)
        n = 2
        for d in range(30):
            for i in range(5):
                eigen_post(self.nep, n, "111", start + timedelta(days=d, hours=i * 2, minutes=30), ["linkedin", "facebook"])
                n += 1
        self.assertEqual([p["tijd"] for p in self.voorstel()["posts"]], [p["tijd"] for p in v["posts"]])

    def test_m6_wissel_van_zernio_naar_metricool(self):
        nz = NepZernio()
        try:
            zz = self.zernio(nz)
            pr.ACCOUNTS.write_text(json.dumps([{"id": "a" * 24, "gebruikersnaam": "mijn_merk"}]))
            ronde_a = self.maak_ronde("ronde-a-zernio")
            with redirect_stdout(io.StringIO()):
                self.voorstel(z=zz, map_=ronde_a)
            self.echt(z=zz, map_=ronde_a)
            zernio_tijden = {datetime.fromisoformat(p["scheduledFor"].replace("Z", "+00:00")) for p in nz.posts.values()}
            pr.ACCOUNTS.write_text(json.dumps([{"id": "111", "gebruikersnaam": "mijn_merk"}]))   # nu via Metricool
            st = self.stand(map_=ronde_a)
            self.assertIn("via Zernio (andere koppeling", st)
            self.assertNotIn("gestopt", st)
            self.assertFalse(any(r.get("status") == "weg" for r in self.boek(ronde_a).values()))
            v = self.voorstel(map_=self.maak_ronde("ronde-b-metricool"))
            alle = sorted(zernio_tijden | {datetime.fromisoformat(p["tijd"]) for p in v["posts"]})
            self.assertEqual(len(alle), 6, "geen minuut dubbel")
            self.assertTrue(all(b - a >= timedelta(minutes=45) for a, b in zip(alle, alle[1:])), "de Zernio-reels tellen mee")
            meldingen = []
            eigen = {k: e for k, e in cijfers.ingepland().items() if e["ronde"] == "ronde-a-zernio"}
            self.assertEqual(cijfers.verzamel(self.z, eigen, 30, datetime.now(timezone.utc), meldingen), [])
            self.assertTrue(any("via Zernio" in m for m in meldingen))
            self.assertFalse([a for a in self.nep.aanroepen if a[2].get("blogId") == "a" * 24], "geen Zernio-id naar Metricool")
        finally:
            nz.stop()

    def test_m7_wissel_naar_zernio_na_weggevallen_antwoord(self):
        self.voorstel()
        self.antwoord_valt_weg()
        nz = NepZernio()
        try:
            zz = self.zernio(nz)
            pr.ACCOUNTS.write_text(json.dumps([{"id": "a" * 24, "gebruikersnaam": "mijn_merk"}]))
            with redirect_stdout(io.StringIO()):
                v = self.voorstel(z=zz)
            self.assertEqual(v["elders"], {"01": "Metricool"}, "alleen die ene reel wacht, de rest gaat gewoon")
            self.assertEqual([p["id"] for p in v["posts"]], ["02", "03"])
            self.echt(z=zz)
            self.assertEqual(sorted(p["content"] for p in nz.posts.values()), ["Caption 2", "Caption 3"])
            self.assertEqual(self.tel_caption("Caption 1"), 1)
        finally:
            nz.stop()

    def test_m8_een_merk_zonder_cijfers_breekt_de_rest_niet(self):
        pr.ACCOUNTS.write_text(json.dumps([{"id": "111", "gebruikersnaam": "mijn_merk"}, {"id": "222", "gebruikersnaam": "klein_merk"}]))
        self.voorstel()
        self.echt()
        verleden = datetime.now(AMS) - timedelta(days=3)
        op_111 = []
        for i, r in enumerate(self.boek().values()):
            self.nep.posts[r["zernio_id"]]["publicationDate"]["dateTime"] = (verleden + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%S")
            self.nep.publiceer(r["zernio_id"], f"C{i}")
            if r["account"] == "111":
                op_111.append(f"C{i}")
        self.nep.stats["111"] = [{"url": f"https://www.instagram.com/reel/{c}/", "views": 100} for c in op_111]

        def kapot(h, pad, q, body):
            if h.command == "GET" and pad == "/stats/instagram/reels" and q.get("blogId") == "222":
                return 500, {"message": "Internal Server Error"}
        vervang_route(self.nep, kapot)
        meldingen = []
        eigen = {k: e for k, e in cijfers.ingepland().items() if e["ronde"] == "keuring-ronde"}
        reels = cijfers.verzamel(self.z, eigen, 30, datetime.now(timezone.utc), meldingen)
        self.assertEqual(len(reels), len(op_111))
        self.assertTrue(any("@klein_merk" in m for m in meldingen))
        self.assertIn("## Let op", cijfers.verslag(reels, cijfers.beoordeel(reels, cfg()["winners"]), cfg(), datetime.now(timezone.utc), meldingen))


class TestLicht(Basis):
    def test_l1_een_onbekende_vorm_is_een_fout_en_geen_lege_agenda(self):
        def object_vorm(h, pad, q, body):
            if h.command == "GET" and pad == "/v2/scheduler/posts":
                return 200, {"data": {"elements": [], "total": 0}}
        vervang_route(self.nep, object_vorm)
        with self.assertRaisesRegex(KoppelFout, "vorm"):
            self.voorstel()

    def test_l2_de_tunnel_toont_alleen_de_reels_van_deze_ronde(self):
        (self.map_ / "klaar" / "oud").mkdir()
        (self.map_ / "klaar" / "oud" / "01-oude-versie.mp4").write_bytes(b"oud")
        with self.z.media([self.map_ / "klaar" / "01.mp4"]):
            adres = self.z._media
            self.assertEqual(urllib.request.urlopen(adres + "/01.mp4", timeout=5).status, 200)
            for pad in ("/", "/01.json", "/02.mp4", "/oud/01-oude-versie.mp4"):
                with self.assertRaises(urllib.error.HTTPError, msg=pad):
                    urllib.request.urlopen(adres + pad, timeout=5)

    def test_l4_geen_tunnel_als_er_niets_te_doen_is(self):
        geteld = []

        @contextlib.contextmanager
        def tel_tunnel(poort):
            geteld.append(poort)
            yield f"http://127.0.0.1:{poort}"
        self.z = self.metricool(tunnel=tel_tunnel)
        self.voorstel()
        self.echt()
        self.assertIn("staat al klaar", self.echt())
        self.assertEqual(len(geteld), 1)

    def test_l5_een_voorstel_van_versie_1_0_is_voor_zernio(self):
        v = self.voorstel()
        v.pop("koppeling")
        pr.schrijf_json(self.map_ / "voorstel.json", v)
        with self.assertRaisesRegex(PlanFout, "koppeling is nu Metricool"):
            self.echt()
        self.assertEqual(self.nep.posts, {})

    def test_l6_een_los_veld_telt_niet_als_postregels_gekozen(self):
        pad = basis.TMP / "keuring-l6" / "config.json"
        ins.schrijf({"posten": {"per_dag": 3}}, pad)
        self.assertIn("de postregels", ins.nog_niet_gekozen(pad))
        ins.schrijf({"posten": {"per_dag": 3, "minuten_tussen": 45, "van": 9, "tot": 21, "tijdzone": "Europe/Amsterdam",
                                "doorzetten": "zelf"}, "winners": {"factor": 3, "min_views": 500}}, pad)
        self.assertEqual(ins.nog_niet_gekozen(pad), [])

    def test_l8_een_ongeldig_veld_neemt_de_rest_niet_mee(self):
        pad = basis.TMP / "keuring-l8" / "config.json"
        pad.parent.mkdir(parents=True, exist_ok=True)
        pad.write_text(json.dumps({"versie": 1, "tekst": {"font": "Bestaat-Niet.ttf", "positie": "onder"},
                                   "posten": {"per_dag": 2, "van": 8, "tot": 12, "tijdzone": "Europe/Amsterdam"},
                                   "winners": {"factor": 5}}))
        self.assertEqual(ins.lees_eigen(pad)[1], ["tekst.font"])
        ins.schrijf({"tekst": {"font": "Anton-Regular.ttf"}}, pad)
        bewaard = json.loads(pad.read_text())
        self.assertEqual(bewaard["tekst"], {"font": "Anton-Regular.ttf", "positie": "onder"})
        self.assertEqual(bewaard["posten"]["per_dag"], 2)
        self.assertEqual(bewaard["winners"], {"factor": 5})

    def test_l8_twee_ongeldige_velden_nemen_de_rest_ook_niet_mee(self):
        pad = basis.TMP / "keuring-l8b" / "config.json"
        pad.parent.mkdir(parents=True, exist_ok=True)
        pad.write_text(json.dumps({"versie": 1, "tekst": {"font": "Bestaat-Niet.ttf", "kleur_tekst": "rood", "positie": "onder"}}))
        goed, weg = ins.lees_eigen(pad)
        self.assertEqual(goed["tekst"], {"positie": "onder"})
        self.assertEqual(sorted(weg), ["tekst.font", "tekst.kleur_tekst"])

    def test_l9_een_merk_zonder_instagramnaam_krijgt_zijn_nummer(self):
        self.nep.merken = [{"id": 555, "label": "Vlag", "instagram": True}, {"id": 556, "label": "Nummer", "instagram": 17841400000001}]
        self.assertEqual([a["gebruikersnaam"] for a in self.z.accounts()], ["merk-555", "merk-556"])


class TestTunnelEnSleutel(unittest.TestCase):
    """Met een nagemaakte cloudflared (een klein script op het pad), zonder contact met Cloudflare."""

    def setUp(self):
        self.bin = basis.TMP / f"bin-{self.id().split('.')[-1]}"
        self.bin.mkdir(parents=True, exist_ok=True)
        self.pidbestand = self.bin / "pid"

    def nep_cloudflared(self, regel):
        script = self.bin / "cloudflared"
        script.write_text(f'#!/bin/bash\necho $$ > "{self.pidbestand}"\necho \'{regel}\'\nexec sleep 300\n')
        script.chmod(0o755)
        return {**os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}"}

    def leeft(self, pid):
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False

    def tearDown(self):
        if self.pidbestand.exists():
            pid = int(self.pidbestand.read_text())
            if self.leeft(pid):
                os.kill(pid, signal.SIGKILL)

    def test_l3_geen_adres_binnen_de_wachttijd_ook_als_cloudflared_zwijgt(self):
        env = self.nep_cloudflared("failed to request quick Tunnel: Post https://api.trycloudflare.com/tunnel")
        with mock.patch.dict(os.environ, env):
            begin = time.monotonic()
            with self.assertRaisesRegex(KoppelFout, "Geen tunnel"):
                with mmod.cloudflared_tunnel(8, wacht=2):
                    pass
        self.assertLess(time.monotonic() - begin, 8)
        self.assertFalse(self.leeft(int(self.pidbestand.read_text())), "cloudflared is weer gestopt")

    def test_l3_een_harde_stop_sluit_de_tunnel(self):
        env = self.nep_cloudflared("|  https://rustig-blauw-paard.trycloudflare.com  |")
        code = ("import sys, time; sys.path.insert(0, sys.argv[1]); import metricool, plan_ronde; plan_ronde.stop_netjes()\n"
                "with metricool.cloudflared_tunnel(8, wacht=10) as adres:\n    print(adres, flush=True); time.sleep(60)\n")
        with subprocess.Popen([sys.executable, "-c", code, str(SCRIPTS)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, env=env) as p:
            self.assertEqual(p.stdout.readline().strip(), "https://rustig-blauw-paard.trycloudflare.com")
            pid = int(self.pidbestand.read_text())
            p.send_signal(signal.SIGTERM)
            p.wait(timeout=15)
            fout = p.stderr.read()
        for _ in range(50):
            if not self.leeft(pid):
                break
            time.sleep(0.1)
        self.assertFalse(self.leeft(pid), "na een SIGTERM draait cloudflared niet als wees door")
        self.assertIn("Gestopt", fout)

    def test_l7_terug_naar_een_bewaarde_koppeling_zonder_nieuwe_sleutel(self):
        import site
        nz, nm = NepZernio(), NepMetricool()
        try:
            nm.merken = [{"id": 111, "label": "Mijn merk", "instagram": "mijn_merk"}]
            thuis = basis.TMP / "thuis-l7"
            map_ = thuis / ".config" / "trial-reels-starter"
            map_.mkdir(parents=True, exist_ok=True)
            (map_ / "zernio-api-key").write_text(SLEUTEL + "\n")
            (map_ / "metricool-token").write_text(TOKEN + "\n")
            env = {**os.environ, "HOME": str(thuis), "PYTHONUSERBASE": site.getuserbase(), "TRS_ZERNIO_BASIS": nz.basis,
                   "TRS_METRICOOL_BASIS": nm.basis}
            draai = lambda *extra: subprocess.run([sys.executable, str(SCRIPTS / "sleutel.py"), *extra], input="",
                                                  capture_output=True, text=True, env=env)
            koppeling.schrijf({"soort": "metricool", "metricool_user": USER})
            r = draai("--bewaard", "zernio")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(koppeling.lees(), {"soort": "zernio", "metricool_user": USER}, "het gebruikersnummer blijft bewaard")
            r = draai("--bewaard", "metricool")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(koppeling.lees()["soort"], "metricool")
            self.assertNotIn(TOKEN, r.stdout + r.stderr)
            self.assertNotIn(SLEUTEL, r.stdout + r.stderr)
        finally:
            koppeling.schrijf({"soort": "zernio"})
            nz.stop()
            nm.stop()


if __name__ == "__main__":
    unittest.main()


def verleden(nep, post_id, uren_terug, map_):
    """Zet een Metricool-post op een moment in het verleden (alsof zijn tijd voorbij is), en het boek mee."""
    t = (datetime.now(AMS) - timedelta(hours=uren_terug)).replace(microsecond=0)
    nep.posts[str(post_id)]["publicationDate"]["dateTime"] = t.strftime("%Y-%m-%dT%H:%M:%S")
    pad = map_ / "ingepland.json"
    boek = json.loads(pad.read_text())
    for r in boek["posts"].values():
        if r.get("zernio_id") == str(post_id):
            r["tijd"] = t.astimezone(timezone.utc).isoformat()
    pad.write_text(json.dumps(boek))


@contextlib.contextmanager
def tussenstation_zonder_lengte(poort):
    """Een tunnel die bij HEAD geen Content-Length doorgeeft (dat mag een tussenstation); GET werkt gewoon."""
    import http.client
    import http.server
    import threading

    class P(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _door(self, met_lijf):
            c = http.client.HTTPConnection("127.0.0.1", poort, timeout=10)
            c.request(self.command, self.path)
            r = c.getresponse()
            lijf = r.read() if met_lijf else b""
            self.send_response(r.status)
            for k, v in r.getheaders():
                if k.lower() not in ("content-length", "connection", "transfer-encoding"):
                    self.send_header(k, v)
            if met_lijf:
                self.send_header("Content-Length", str(len(lijf)))
            self.end_headers()
            self.wfile.write(lijf)
            c.close()

        def do_GET(self):
            self._door(True)

        def do_HEAD(self):
            self._door(False)

    s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), P)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{s.server_address[1]}"
    finally:
        s.shutdown()
        s.server_close()


class TestHerkeuring(Basis):
    """De tweede keuring (19 okt 2026): wat de eerste reparatie zelf nog fout deed."""

    def voeg_reel_toe(self, pid, caption):
        ronde = json.loads((self.map_ / "ronde.json").read_text())
        p = {"id": pid, "video": f"weg/{pid}.mp4", "tekst": f"Tekst {pid}", "caption": caption}
        ronde["posts"].append(p)
        (self.map_ / "klaar" / f"{pid}.mp4").write_bytes(b"\0" * 2000 + pid.encode())
        (self.map_ / "klaar" / f"{pid}.json").write_text(json.dumps(mr.vingerafdruk(p, cfg())))
        (self.map_ / "ronde.json").write_text(json.dumps(ronde))

    def alles_online_en_voorbij(self):
        self.voorstel()
        self.echt()
        b = self.boek()
        for i, (pid, r) in enumerate(sorted(b.items())):
            verleden(self.nep, r["zernio_id"], 80 - i, self.map_)
            self.nep.publiceer(r["zernio_id"], f"CODE{pid}")
        return b

    def test_n1_verwijderd_na_zijn_tijd_gaat_niet_opnieuw(self):
        b = self.alles_online_en_voorbij()          # geen --stand: in het boek staat nog 'pending'
        del self.nep.posts[b["01"]["zernio_id"]]     # de gebruiker ruimt zijn planner op
        self.nep.posts[b["02"]["zernio_id"]]["deleted"] = True
        self.voeg_reel_toe("04", "Caption 4")
        v = self.voorstel()
        self.assertEqual(v["opnieuw"], [])
        self.assertEqual([p["id"] for p in v["posts"]], ["04"])
        self.echt()
        self.assertEqual(self.tel_caption("Caption 1"), 0, "01 stond al op Instagram en komt er niet nog eens")
        st = self.stand()
        self.assertIn("kan al online staan", st)

    def test_n1_zernio_verwijderd_na_zijn_tijd_gaat_niet_opnieuw(self):
        nz = NepZernio()
        try:
            zz = self.zernio(nz)
            pr.ACCOUNTS.write_text(json.dumps([{"id": "a" * 24, "gebruikersnaam": "mijn_merk"}]))
            with redirect_stdout(io.StringIO()):
                self.voorstel(z=zz)
            self.echt(z=zz)
            b = self.boek()
            for pid, r in b.items():
                p = nz.posts[r["zernio_id"]]
                p["scheduledFor"] = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
                r["tijd"] = p["scheduledFor"].replace("Z", "+00:00")
                p["status"] = "published"
                p["platforms"][0].update(status="published", platformPostUrl=f"https://www.instagram.com/reel/Z{pid}/")
            pr.schrijf_json(self.map_ / "ingepland.json", {"posts": b})
            nz.posts.pop(b["01"]["zernio_id"])
            self.voeg_reel_toe("04", "Caption 4")
            with redirect_stdout(io.StringIO()):
                v = self.voorstel(z=zz)
            self.assertEqual(v["opnieuw"], [])
            self.assertEqual([p["id"] for p in v["posts"]], ["04"])
        finally:
            nz.stop()

    def test_n2_na_nakijken_bij_de_oude_koppeling_mag_de_nieuwe_wel(self):
        nz = NepZernio()
        try:
            zz = self.zernio(nz)
            pr.ACCOUNTS.write_text(json.dumps([{"id": "a" * 24, "gebruikersnaam": "mijn_merk"}]))
            with redirect_stdout(io.StringIO()):
                self.voorstel(z=zz)
            nz.storing = [(r"POST /api/v1/media/presign$", 400)]      # de upload van 01 lukt niet; Zernio krijgt niets
            with self.assertRaises(KoppelFout), redirect_stdout(io.StringIO()):
                pr.echt(self.map_, mr.lees_ronde(self.map_, bron=False), cfg(), zz)
            pr.ACCOUNTS.write_text(json.dumps([{"id": "111", "gebruikersnaam": "mijn_merk"}]))
            v = self.voorstel()
            self.assertEqual(v["elders"], {"01": "Zernio"})
            self.assertEqual([p["id"] for p in v["posts"]], ["02", "03"])
            pr.ACCOUNTS.write_text(json.dumps([{"id": "a" * 24, "gebruikersnaam": "mijn_merk"}]))
            with redirect_stdout(io.StringIO()):
                self.voorstel(z=zz)                                    # Zernio kijkt: niets
            pr.ACCOUNTS.write_text(json.dumps([{"id": "111", "gebruikersnaam": "mijn_merk"}]))
            v = self.voorstel()
            self.assertEqual(v["elders"], {})
            self.assertEqual([p["id"] for p in v["posts"]], ["01", "02", "03"])
        finally:
            nz.stop()

    def test_n2_vrijgeven_als_de_oude_koppeling_er_niet_meer_is(self):
        self.voorstel()
        self.antwoord_valt_weg()
        self.nep.posts.clear()           # de gebruiker keek in Metricool: 01 staat er niet
        with self.assertRaisesRegex(PlanFout, "niet half ingepland"), redirect_stdout(io.StringIO()):
            pr.vrijgeven(self.map_, ["02"])
        with redirect_stdout(io.StringIO()):
            pr.vrijgeven(self.map_, ["01"])
        self.assertTrue(self.boek()["01"]["nagekeken"])

    def test_n3_teruggevonden_post_zonder_video_heet_mislukt(self):
        self.voorstel()
        self.nep.kopie_lukt = False
        self.antwoord_valt_weg()                     # 01 staat bij Metricool met het tunneladres; het antwoord viel weg
        self.nep.kopie_lukt = True
        uit = self.echt()
        self.assertIn("al bij Metricool: 01", uit)
        self.assertIn("MISLUKT: 01", uit)
        self.assertIn("video kwam niet aan", self.boek()["01"]["fout"])
        self.assertIn("1 mislukt bij het inplannen", self.stand())

    def test_n3_teruggevonden_gewone_reel_heet_mislukt(self):
        eerste = []

        def als_reel(h, pad, q, body):
            if h.command == "POST" and pad == "/v2/scheduler/posts" and body and not eerste:
                eerste.append(1)
                body["instagramData"] = {**body["instagramData"], "type": "REEL"}
        vervang_route(self.nep, als_reel)
        self.voorstel()
        self.antwoord_valt_weg()
        uit = self.echt()
        self.assertIn("MISLUKT: 01", uit)
        self.assertIn("gewone reel", self.boek()["01"]["fout"])

    def test_n3_terughalen_mislukt_dan_controle_bij_de_volgende_keer(self):
        self.voorstel()
        self.nep.kopie_lukt = False
        self.nep.storing = [(r"GET /api/v2/scheduler/posts/\d+$", 503)] * 3
        with self.assertRaises(KoppelFout), redirect_stdout(io.StringIO()):
            pr.echt(self.map_, mr.lees_ronde(self.map_, bron=False), cfg(), self.z)
        self.nep.kopie_lukt = True
        self.assertIn("MISLUKT: 01", self.echt())

    def test_n3_geen_antwoord_op_de_post_eerst_terugzoeken(self):
        self.voorstel()
        self.nep.storing = [(r"POST /api/v2/scheduler/posts$", "slik")]
        self.assertIn("3 reels ingepland", self.echt(), "teruggevonden in dezelfde run, niet opnieuw gemaakt")
        self.assertEqual(self.tel_caption("Caption 1"), 1)

    def test_n4_een_tunnel_zonder_lengte_bij_head_werkt(self):
        self.z = self.metricool(tunnel=tussenstation_zonder_lengte)
        self.voorstel()
        self.assertIn("3 reels ingepland", self.echt())
        self.assertTrue(all(p["media"][0].startswith("https://static.metricool.com/") for p in self.nep.posts.values()))

    def test_n5_zelf_opnieuw_gezet_in_metricool_gaat_niet_nog_eens(self):
        self.voorstel()
        self.echt()
        b = self.boek()
        oud = self.nep.posts[b["01"]["zernio_id"]]
        verleden(self.nep, b["01"]["zernio_id"], 1, self.map_)
        self.nep.publiceer(b["01"]["zernio_id"], None, fout="Instagram gaf een fout")
        t = datetime.now(AMS) + timedelta(days=2, hours=3)
        self.nep.posts["777777"] = {**json.loads(json.dumps(oud)), "id": 777777,   # door de gebruiker: nieuw id, zelfde caption
                                    "publicationDate": {"dateTime": t.strftime("%Y-%m-%dT%H:%M:%S"), "timezone": "Europe/Amsterdam"},
                                    "providers": [{"network": "instagram", "status": "PENDING"}]}
        self.voeg_reel_toe("04", "Caption 4")
        v = self.voorstel()
        self.assertEqual(v["zelf_opnieuw"], ["01"])
        self.assertEqual(v["opnieuw"], [])
        self.echt()
        self.assertEqual(sum(1 for p in self.nep.posts.values() if p["text"] == "Caption 1" and p["providers"][0]["status"] == "PENDING"), 1)

    def test_n5_mislukt_zonder_eigen_herstel_gaat_wel_opnieuw(self):
        self.voorstel()
        self.echt()
        b = self.boek()
        verleden(self.nep, b["01"]["zernio_id"], 1, self.map_)
        self.nep.publiceer(b["01"]["zernio_id"], None, fout="Instagram gaf een fout")
        v = self.voorstel()
        self.assertEqual(v["opnieuw"], ["01"])

    def test_n6_een_verzette_reel_laat_echt_niet_rondgaan(self):
        self.voorstel()
        self.echt()
        b = self.boek()
        p02 = self.nep.posts[b["02"]["zernio_id"]]
        oud = datetime.fromisoformat(p02["publicationDate"]["dateTime"])
        p02["publicationDate"]["dateTime"] = (oud + timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%S")
        self.voeg_reel_toe("04", "Caption 4")
        self.voorstel()
        self.assertIn("1 reels ingepland", self.echt())
        nieuw = datetime.fromisoformat(self.boek()["02"]["tijd"]).astimezone(AMS).replace(tzinfo=None)
        self.assertEqual(nieuw, oud + timedelta(hours=6), "het boek kent de nieuwe tijd")

    def test_n7_velden_die_alleen_samen_kloppen_blijven(self):
        pad = basis.TMP / "keuring-n7" / "config.json"
        pad.parent.mkdir(parents=True, exist_ok=True)
        pad.write_text(json.dumps({"versie": 1, "posten": {"per_dag": 99, "van": 22, "tot": 24, "minuten_tussen": 60,
                                                           "tijdzone": "Europe/Amsterdam", "doorzetten": "zelf"}}))
        goed, weg = ins.lees_eigen(pad)
        self.assertEqual(weg, ["posten.per_dag"])
        self.assertEqual((goed["posten"]["van"], goed["posten"]["tot"]), (22, 24))

    def test_n8_een_kapot_boek_van_een_andere_ronde_stopt_het_voorstel(self):
        ander = self.maak_ronde("keuring-kapot")
        (ander / "ingepland.json").write_text('{"posts": {"01": {"zernio_id": "1"')
        with self.assertRaisesRegex(PlanFout, "beschadigd"):
            self.voorstel()
        (ander / "ingepland.json").write_text(json.dumps({"posts": ["kapot"]}))
        with self.assertRaisesRegex(PlanFout, "vorm"):
            self.voorstel()
        self.assertEqual(self.nep.posts, {})

    def test_n9_bewaard_ook_bij_een_kapot_koppelbestand(self):
        import site
        nz = NepZernio()
        try:
            thuis = basis.TMP / "thuis-n9"
            (thuis / ".config" / "trial-reels-starter").mkdir(parents=True, exist_ok=True)
            (thuis / ".config" / "trial-reels-starter" / "zernio-api-key").write_text(SLEUTEL + "\n")
            koppeling.BESTAND.write_text("{kapot")
            env = {**os.environ, "HOME": str(thuis), "PYTHONUSERBASE": site.getuserbase(), "TRS_ZERNIO_BASIS": nz.basis}
            r = subprocess.run([sys.executable, str(SCRIPTS / "sleutel.py"), "--bewaard", "zernio"], input="",
                               capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(koppeling.lees()["soort"], "zernio")
        finally:
            nz.stop()
