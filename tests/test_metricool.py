"""De Metricool-koppeling: inplannen, nooit dubbel, video's die aankomen, de stand en de cijfers."""

import contextlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import unittest
from unittest import mock
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import basis
import cijfers
import instellingen as ins
import koppeling
import maak_reels as mr
import plan_ronde as pr
from koppelfout import KoppelFout
from metricool import Metricool
from nep_metricool import TOKEN, USER, NepMetricool

TMP = basis.TMP / "metricool"
AMS = ZoneInfo("Europe/Amsterdam")


def cfg(**posten):
    c = ins.keur(json.loads(ins.STANDAARD.read_text(encoding="utf-8")))
    c["posten"].update(posten)
    return c


@contextlib.contextmanager
def lokale_tunnel(poort):
    """In de tests geen cloudflared: de nagemaakte Metricool haalt de video rechtstreeks van de lokale server."""
    yield f"http://127.0.0.1:{poort}"


@contextlib.contextmanager
def kapotte_tunnel(poort):
    yield "http://127.0.0.1:9"   # hier luistert niemand: de video komt nooit aan


class TestMetricool(unittest.TestCase):
    def setUp(self):
        self.nep = NepMetricool()
        self.nep.merken = [{"id": 111, "label": "Mijn merk", "instagram": "mijn_merk"},
                           {"id": 222, "label": "Klein merk", "instagram": "klein_merk"},
                           {"id": 333, "label": "Alleen Facebook", "facebook": "pagina"}]
        self.nep.volgers = {"111": 1500, "222": 40}
        self.z = self.metricool()
        self.map_ = ins.MIJN / "rondes" / "metricool-ronde"   # cijfers.py leest de rondes uit mijn-trial-reels/rondes
        if self.map_.exists():
            shutil.rmtree(self.map_)
        (self.map_ / "klaar").mkdir(parents=True)
        self.posts = [{"id": f"0{i}", "video": f"weg/0{i}.mp4", "tekst": f"Tekst {i}", "caption": f"Caption {i}"} for i in range(1, 4)]
        for p in self.posts:
            (self.map_ / "klaar" / f"{p['id']}.mp4").write_bytes(b"\0" * 2000 + p["id"].encode())
            (self.map_ / "klaar" / f"{p['id']}.json").write_text(json.dumps(mr.vingerafdruk(p, cfg())))
        (self.map_ / "ronde.json").write_text(json.dumps({"naam": "ronde", "posts": self.posts}))
        ins.MIJN.mkdir(parents=True, exist_ok=True)
        pr.ACCOUNTS.write_text(json.dumps([{"id": "111", "gebruikersnaam": "mijn_merk"}]))

    def tearDown(self):
        self.nep.stop()

    def metricool(self, tunnel=lokale_tunnel):
        return Metricool(user_id=USER, tijdzone="Europe/Amsterdam", token=TOKEN, basis=self.nep.basis, pauze=0,
                         slaap=lambda s: None, tunnel=tunnel)

    def ronde(self):
        return mr.lees_ronde(self.map_, bron=False)

    def voorstel(self, c=None):
        v = pr.voorstel(self.map_, self.ronde(), c or cfg(), self.z, "auto", None)
        pr.schrijf_json(self.map_ / "voorstel.json", v)
        return v

    def echt(self, c=None):
        with redirect_stdout(io.StringIO()) as uit:
            pr.echt(self.map_, self.ronde(), c or cfg(), self.z)
        return uit.getvalue()

    def boek(self):
        return json.loads((self.map_ / "ingepland.json").read_text())["posts"]

    def test_accounts_zijn_merken_met_instagram(self):
        lijst = {a["gebruikersnaam"]: a for a in self.z.accounts()}
        self.assertEqual(set(lijst), {"mijn_merk", "klein_merk"}, "een merk zonder Instagram telt niet")
        self.assertEqual(lijst["mijn_merk"]["id"], "111")
        self.assertEqual(lijst["mijn_merk"]["volgers"], 1500)
        del self.nep.volgers["222"]
        self.assertIsNone({a["gebruikersnaam"]: a for a in self.z.accounts()}["klein_merk"]["volgers"])

    def test_voorstel_plant_minstens_een_uur_vooruit(self):
        v = self.voorstel()
        self.assertEqual(v["koppeling"], "Metricool")
        nu = datetime.now(timezone.utc)
        self.assertTrue(all(datetime.fromisoformat(p["tijd"]) - nu >= timedelta(minutes=60) for p in v["posts"]))
        self.assertFalse([a for a in self.nep.aanroepen if a[0] == "POST"], "een voorstel plant niets in")

    def test_een_plek_binnen_het_uur_slaat_metricool_over(self):
        # Onafhankelijk van de klok van nu: een vaste plek ligt 30 minuten vooruit, en Metricool wil minstens een uur
        import planning
        p = cfg()["posten"]
        dag = (datetime.now(AMS) + timedelta(days=2)).date()
        nu = (planning.dagtijden(dag, p)[1] - timedelta(minutes=30)).astimezone(timezone.utc)
        (_, _, tijd), = planning.plan([("01", None)], ["111"], {"111": []}, p, nu, marge=self.z.marge_minuten)
        self.assertGreaterEqual(tijd - nu, timedelta(minutes=60))

    def test_echt_plant_trial_reels_met_de_video_bij_metricool(self):
        v = self.voorstel(cfg(doorzetten="automatisch"))
        uit = self.echt(cfg(doorzetten="automatisch"))
        self.assertIn("3 reels ingepland. Metricool zet ze", uit)
        posts = sorted(self.nep.posts.values(), key=lambda p: p["publicationDate"]["dateTime"])
        self.assertEqual(len(posts), 3)
        for p, verwacht in zip(posts, v["posts"]):
            self.assertEqual(p["_blog"], "111")
            self.assertEqual(p["instagramData"]["type"], "TRIAL_REEL")
            self.assertTrue(p["instagramData"]["shareTrialAutomatically"])
            self.assertEqual(p["providers"], [{"network": "instagram", "status": "PENDING"}])
            self.assertTrue(p["media"][0].startswith("https://static.metricool.com/"), "de video is bij Metricool aangekomen")
            lokaal = datetime.fromisoformat(verwacht["tijd"]).astimezone(AMS).strftime("%Y-%m-%dT%H:%M:%S")
            self.assertEqual(p["publicationDate"], {"dateTime": lokaal, "timezone": "Europe/Amsterdam"})
        self.assertEqual(sorted(p["text"] for p in posts), ["Caption 1", "Caption 2", "Caption 3"])
        self.assertFalse(any("video_url" in r for r in self.boek().values()), "een tunneladres wordt niet bewaard")

    def test_onder_200_volgers_een_gewone_reel(self):
        pr.ACCOUNTS.write_text(json.dumps([{"id": "222", "gebruikersnaam": "klein_merk"}]))
        self.voorstel()
        self.echt()
        self.assertEqual({p["instagramData"]["type"] for p in self.nep.posts.values()}, {"REEL"})

    def test_weggevallen_antwoord_geeft_geen_tweede_post(self):
        self.voorstel()
        # Het antwoord valt weg, en terugzoeken lukt in die run ook niet (Metricool even onbereikbaar)
        from test_keuring_metricool import valt_weg
        valt_weg(self.nep)
        with self.assertRaises(KoppelFout), redirect_stdout(io.StringIO()):
            pr.echt(self.map_, self.ronde(), cfg(), self.z)
        self.assertEqual(len(self.nep.posts), 1, "Metricool kreeg hem wel")
        uit = self.echt()
        self.assertIn("al bij Metricool: 01", uit)
        self.assertEqual(len(self.nep.posts), 3, "teruggevonden op tijd en caption, niet opnieuw gemaakt")
        self.assertTrue(all(r.get("zernio_id") for r in self.boek().values()))

    def test_tunnel_die_niet_werkt_plant_niets(self):
        self.z = self.metricool(tunnel=kapotte_tunnel)
        self.voorstel()
        with self.assertRaisesRegex(KoppelFout, "niet bereikbaar"), redirect_stdout(io.StringIO()):
            pr.echt(self.map_, self.ronde(), cfg(), self.z)
        self.assertEqual(self.nep.posts, {}, "eerst kijken of de video op te halen is, dan pas inplannen")

    def test_video_die_niet_aankomt_heet_mislukt_en_kan_daarna_opnieuw(self):
        self.nep.kopie_lukt = False
        self.voorstel()
        uit = self.echt()
        self.assertIn("MISLUKT", uit)
        self.assertIn("video kwam niet aan bij Metricool", uit)
        self.assertIn("0 reels ingepland", uit)
        with redirect_stdout(io.StringIO()) as st:
            pr.stand(self.map_, self.ronde(), cfg(), self.z)
        self.assertIn("3 mislukt bij het inplannen", st.getvalue(), "niet 'gepland': de post gaat zo nooit goed")
        with self.assertRaisesRegex(pr.PlanFout, "stopt die post daar eerst"):
            self.voorstel()
        self.nep.posts.clear()            # de gebruiker stopt de drie posts in Metricool
        self.nep.kopie_lukt = True
        v = self.voorstel()
        self.assertEqual(v["opnieuw"], ["01", "02", "03"])
        self.assertIn("3 reels ingepland", self.echt())
        self.assertEqual(len(self.nep.posts), 3)
        self.assertTrue(all(p["media"][0].startswith("https://static.metricool.com/") for p in self.nep.posts.values()))
        b = self.boek()
        self.assertTrue(all(r["zernio_id"] and not r.get("fout") and r["eerder"][0]["status"] == "weg" for r in b.values()),
                        "de mislukte poging staat nog in het boek, onder eerder")

    def test_stand_gepland_mislukt_en_weg(self):
        self.voorstel()
        self.echt()
        b = self.boek()
        self.nep.publiceer(b["01"]["zernio_id"], "ABC123")
        self.nep.publiceer(b["02"]["zernio_id"], None, fout="Media type not supported")
        del self.nep.posts[b["03"]["zernio_id"]]
        with redirect_stdout(io.StringIO()) as uit:
            pr.stand(self.map_, self.ronde(), cfg(), self.z)
        t = uit.getvalue()
        self.assertIn("1 online", t)
        self.assertIn("1 mislukt", t)
        self.assertIn("1 niet meer bij Metricool", t)
        self.assertIn("Media type not supported", t)
        self.assertEqual(self.boek()["01"]["url"], "https://www.instagram.com/reel/ABC123/")

    def test_eigen_posts_in_metricool_tellen_mee(self):
        v = self.voorstel()
        eerste = datetime.fromisoformat(v["posts"][0]["tijd"]).astimezone(AMS)
        self.nep.posts["1"] = {"id": 1, "_blog": "111", "text": "Iets van de klant zelf", "media": [], "draft": False,
                               "publicationDate": {"dateTime": eerste.strftime("%Y-%m-%dT%H:%M:%S"), "timezone": "Europe/Amsterdam"},
                               "providers": [{"network": "instagram", "status": "PENDING"}]}
        v2 = self.voorstel()
        alle = sorted([eerste] + [datetime.fromisoformat(p["tijd"]) for p in v2["posts"]])
        self.assertTrue(all(b - a >= timedelta(minutes=45) for a, b in zip(alle, alle[1:])))

    def test_cijfers_en_winner_via_metricool(self):
        self.voorstel()
        self.echt()
        b = self.boek()
        verleden = datetime.now(AMS) - timedelta(days=3)
        for i, (pid, code, views) in enumerate([("01", "AAA", 100), ("02", "BBB", 120), ("03", "CCC", 2000)]):
            post = self.nep.posts[b[pid]["zernio_id"]]
            post["publicationDate"]["dateTime"] = (verleden + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%S")
            self.nep.publiceer(b[pid]["zernio_id"], code)
        self.nep.stats["111"] = [{"url": f"https://www.instagram.com/reel/{c}/", "views": v, "reach": v, "likes": 1, "comments": 0,
                                  "saved": 2, "averageWatchTime": 3000} for c, v in (("AAA", 100), ("BBB", 120), ("CCC", 2000))]
        eigen = {k: v for k, v in cijfers.ingepland().items() if v["ronde"] == "metricool-ronde"}
        reels = cijfers.verzamel(self.z, eigen, 30, datetime.now(timezone.utc))
        self.assertEqual(len(reels), 3)
        cijfers.beoordeel(reels, cfg()["winners"])
        self.assertEqual({r["id"] for r in reels if r["winner"]}, {"03"})
        self.assertEqual(next(r for r in reels if r["id"] == "03")["saves"], 2)

    def test_koppeling_kiest_metricool_uit_het_bestand(self):
        koppeling.schrijf({"soort": "metricool", "metricool_user": USER})
        try:
            with mock.patch.dict(os.environ, {"TRS_METRICOOL_TOKEN": TOKEN}):
                import metricool as mmod
                with mock.patch.object(mmod, "TOKENBESTAND", TMP / "geen-token"):
                    self.assertEqual(koppeling.maak(cfg()).naam, "Metricool")
        finally:
            koppeling.schrijf({"soort": "zernio"})
        with self.assertRaises(KoppelFout):
            koppeling.schrijf({"soort": "buffer"})
            koppeling.lees()
        koppeling.schrijf({"soort": "zernio"})

    def test_sleutel_voor_metricool(self):
        import site
        thuis = basis.TMP / "thuis-mc"
        env = {**os.environ, "HOME": str(thuis), "PYTHONUSERBASE": site.getuserbase(), "TRS_METRICOOL_BASIS": self.nep.basis}
        script = str(basis.REPO / "engine" / "scripts" / "sleutel.py")
        draai = lambda waarde, *extra: subprocess.run([sys.executable, script, "--metricool", *extra], input=waarde,
                                                      capture_output=True, text=True, env=env)
        self.assertIn("gebruikersnummer", draai(TOKEN).stderr)
        self.assertIn("niet aan", draai(TOKEN, "--user", "999").stderr)
        bestand = thuis / ".config" / "trial-reels-starter" / "metricool-token"
        self.assertFalse(bestand.exists())
        r = draai(TOKEN, "--user", USER)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn(TOKEN, r.stdout + r.stderr)
        self.assertEqual(stat.S_IMODE(bestand.stat().st_mode), 0o600)
        self.assertEqual(koppeling.lees(), {"soort": "metricool", "metricool_user": USER})
        koppeling.schrijf({"soort": "zernio"})


if __name__ == "__main__":
    unittest.main()
