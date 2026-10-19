"""Tests voor de punten uit de eerste keuring (19 okt 2026), elk met het nummer van de bevinding."""

import io
import json
import os
import shutil
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import basis
import cijfers
import instellingen as ins
import koppel
import maak_reels as mr
import plan_ronde as pr
import zernio as zmod
from nep_zernio import SLEUTEL, NepZernio
from planning import PlanFout
from slot import SlotFout, slot
from tekstblok import TekstFout, render
from zernio import TAG, Zernio, ZernioFout

TMP = basis.TMP / "keuring"
SCRIPTS = basis.REPO / "engine" / "scripts"


def cfg():
    return ins.keur(json.loads(ins.STANDAARD.read_text(encoding="utf-8")))


def schrijf_ronde(map_, posts):
    map_.mkdir(parents=True, exist_ok=True)
    (map_ / "ronde.json").write_text(json.dumps({"naam": map_.name, "posts": posts}), encoding="utf-8")


def draai(script, *args, env=None):
    return subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)], capture_output=True, text=True,
                          env={**os.environ, **(env or {})})


class TestMaken(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TMP.mkdir(parents=True, exist_ok=True)
        # 8 seconden beeld met maar 4 seconden geluid, zoals bij een geknipte clip
        basis.maak_video(TMP / "kort-geluid-tmp.mp4", 1080, 1920, 8, geluid=False)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(TMP / "kort-geluid-tmp.mp4"),
                        "-f", "lavfi", "-i", "sine=f=440:d=4", "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
                        str(TMP / "kort-geluid.mp4")], check=True)
        basis.maak_video(TMP / "staand.mp4", 1080, 1920, 4)

    def map_(self, naam):
        m = TMP / naam
        if m.exists():
            shutil.rmtree(m)
        return m

    def test_1_geluid_korter_dan_beeld_kort_de_reel_niet_in(self):
        m = self.map_("k1")
        schrijf_ronde(m, [{"id": "01", "video": str(TMP / "kort-geluid.mp4"), "tekst": "Hallo"}])
        r = draai("maak_reels.py", m)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertAlmostEqual(mr.meet(m / "klaar" / "01.mp4")["duur"], 8, delta=0.15)

    def test_1_een_mislukte_reel_komt_nooit_in_klaar(self):
        m = self.map_("k2")
        schrijf_ronde(m, [{"id": "01", "video": str(TMP / "staand.mp4"), "tekst": "Hallo"}])
        ronde = mr.lees_ronde(m)
        echt_meten = mr.meet

        def nep_meten(pad):
            uit = echt_meten(pad)
            return {**uit, "duur": 1.0} if Path(pad).name.startswith(".") else uit
        with mock.patch.object(mr, "meet", nep_meten), self.assertRaises(mr.RondeFout):
            mr.maak_een(m, ronde["posts"][0], echt_meten(TMP / "staand.mp4"), cfg())
        self.assertFalse((m / "klaar" / "01.mp4").exists())
        self.assertEqual(len(list((m / "klaar" / "mislukt").glob("01-*.mp4"))), 1, "de mislukte poging staat opzij")
        self.assertFalse(mr.actueel(m, ronde["posts"][0], cfg()))

    def test_1_een_halve_reel_van_een_onderbreking_wordt_overgedaan(self):
        m = self.map_("k3")
        schrijf_ronde(m, [{"id": "01", "video": str(TMP / "staand.mp4"), "tekst": "Hallo"}])
        (m / "klaar").mkdir()
        (m / "klaar" / ".01.bezig.mp4").write_bytes(b"half")
        r = draai("maak_reels.py", m)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("1 gemaakt", r.stdout)
        self.assertEqual(len(list((m / "klaar" / "mislukt").glob("01-*.mp4"))), 1)
        self.assertAlmostEqual(mr.meet(m / "klaar" / "01.mp4")["duur"], 4, delta=0.15)

    def test_4_andere_tekst_of_stijl_maakt_de_reel_opnieuw_en_bewaart_de_oude(self):
        m = self.map_("k4")
        schrijf_ronde(m, [{"id": "01", "video": str(TMP / "staand.mp4"), "tekst": "Oude tekst"}])
        self.assertEqual(draai("maak_reels.py", m).returncode, 0)
        self.assertIn("0 gemaakt", draai("maak_reels.py", m).stdout, "niets veranderd: niets opnieuw")
        schrijf_ronde(m, [{"id": "01", "video": str(TMP / "staand.mp4"), "tekst": "Nieuwe tekst"}])
        self.assertFalse(mr.actueel(m, mr.lees_ronde(m)["posts"][0], cfg()))
        r = draai("maak_reels.py", m)
        self.assertIn("opnieuw", r.stdout)
        self.assertTrue(mr.actueel(m, mr.lees_ronde(m)["posts"][0], cfg()))
        self.assertEqual(len(list((m / "klaar" / "oud").glob("01-*.mp4"))), 1)
        # Een andere stijl telt ook
        c = cfg()
        c["tekst"]["grootte"] = "groot"
        self.assertFalse(mr.actueel(m, mr.lees_ronde(m)["posts"][0], c))

    def test_6_bron_weg_na_het_maken_blokkeert_niets(self):
        m = self.map_("k5")
        bron = m / "bron.mp4"
        m.mkdir()
        shutil.copy(TMP / "staand.mp4", bron)
        schrijf_ronde(m, [{"id": "01", "video": "bron.mp4", "tekst": "Hallo"}])
        self.assertEqual(draai("maak_reels.py", m).returncode, 0)
        bron.rename(m / "elders.mp4")
        r = draai("maak_reels.py", m)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("0 gemaakt", r.stdout)
        self.assertTrue(mr.actueel(m, mr.lees_ronde(m, bron=False)["posts"][0], cfg()))

    def test_2_nooit_twee_keer_tegelijk_maken(self):
        m = self.map_("k6")
        schrijf_ronde(m, [{"id": "01", "video": str(TMP / "staand.mp4"), "tekst": "Hallo"}])
        with slot(m, "maken"):
            r = draai("maak_reels.py", m)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Er loopt al iets", r.stderr)
        self.assertFalse((m / "klaar" / "01.mp4").exists())
        self.assertEqual(draai("maak_reels.py", m).returncode, 0, "na het slot gaat het gewoon")

    def test_2_een_slot_van_een_proces_dat_niet_meer_bestaat_telt_niet(self):
        m = self.map_("k7")
        m.mkdir()
        (m / ".maken.slot").write_text("999999")
        with slot(m, "maken"):
            self.assertEqual((m / ".maken.slot").read_text(), str(os.getpid()))
        self.assertFalse((m / ".maken.slot").exists())


class TestTekst(unittest.TestCase):
    def test_7_tekens_die_niet_kunnen_geven_een_fout_in_plaats_van_stil_weg_te_vallen(self):
        for tekst in ["Stap 1 → stap 2", "✓ klaar", "★★★", "① eerst"]:
            with self.assertRaises(TekstFout, msg=tekst):
                render(tekst, cfg())
        for tekst in ["Hoi \U0001F44B\U0001F3FD", "Nederland \U0001F1F3\U0001F1F1", "Gezin \U0001F468‍\U0001F469‍\U0001F467"]:
            with self.assertRaisesRegex(TekstFout, "Vlaggen", msg=tekst):
                render(tekst, cfg())
        render("Kijk \U0001F447 hier ❤️", cfg())

    def test_10_nooit_breder_dan_860(self):
        for tekst, stijl in [("Ondernemersvaardigheden", {}), ("Contentkalender", {"vorm": "rand", "grootte": "groot", "font": "Montserrat-Black.ttf"})]:
            c = cfg()
            c["tekst"].update(stijl)
            try:
                x0, _, x1, _ = render(tekst, c).getchannel("A").getbbox()
                self.assertLessEqual(x1 - x0, 860, tekst)
            except TekstFout:
                pass   # te breed, ook kleiner: dan een fout, nooit over de knoppen
        x0, _, x1, _ = render("Ondernemersvaardigheden", cfg()).getchannel("A").getbbox()
        self.assertLessEqual(x1 - x0, 860, "een lang Nederlands woord past door een iets kleinere letter")

    def test_11_onder_blijft_boven_de_caption(self):
        c = cfg()
        c["tekst"]["positie"] = "onder"
        self.assertLessEqual(render("Twee regels\nonderin", c).getchannel("A").getbbox()[3], 1252)


class TestInplannen(unittest.TestCase):
    def setUp(self):
        self.nep = NepZernio()
        self.nep.accounts = [{"_id": "a" * 24, "platform": "instagram", "profileId": {"_id": "p" * 24}, "username": "groot",
                              "isActive": True, "followersCount": 900}]
        self.z = Zernio(sleutel=SLEUTEL, basis=self.nep.basis, pauze=0, slaap=lambda s: None)
        self.map_ = TMP / "plan"
        if self.map_.exists():
            shutil.rmtree(self.map_)
        (self.map_ / "klaar").mkdir(parents=True)
        self.posts = [{"id": f"0{i}", "video": f"weg/0{i}.mp4", "tekst": f"Tekst {i}", "caption": f"Caption {i}"} for i in range(1, 4)]
        for p in self.posts:
            (self.map_ / "klaar" / f"{p['id']}.mp4").write_bytes(b"\0" * 900 + p["id"].encode())
            (self.map_ / "klaar" / f"{p['id']}.json").write_text(json.dumps(mr.vingerafdruk(p, cfg())))
        schrijf_ronde(self.map_, self.posts)
        ins.MIJN.mkdir(parents=True, exist_ok=True)
        pr.ACCOUNTS.write_text(json.dumps([{"id": "a" * 24, "gebruikersnaam": "groot"}]))

    def tearDown(self):
        self.nep.stop()

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

    def test_2_nooit_twee_keer_tegelijk_inplannen(self):
        self.voorstel()
        # Een eigen HOME zodat een echte sleutel op deze Mac nooit meedoet; de Python-onderdelen van de gebruiker blijven vindbaar
        import site
        env = {"TRS_MIJN": str(ins.MIJN), "TRS_ZERNIO_BASIS": self.nep.basis, "TRS_ZERNIO_API_KEY": SLEUTEL,
               "HOME": str(basis.TMP / "thuis-leeg"), "PYTHONUSERBASE": site.getuserbase()}
        with slot(self.map_, "inplannen"):
            r = draai("plan_ronde.py", self.map_, "--echt", env=env)
        self.assertIn("Er loopt al iets", r.stderr)
        self.assertEqual(len(self.nep.posts), 0)
        r = draai("plan_ronde.py", self.map_, "--echt", env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.nep.posts), 3)

    def test_3_het_voorstel_na_een_weggevallen_antwoord_toont_wat_er_echt_staat(self):
        eerste = self.voorstel()
        self.nep.storing = [(r"POST /api/v1/posts$", "slik")] * 3
        with self.assertRaises(ZernioFout), redirect_stdout(io.StringIO()):
            pr.echt(self.map_, self.ronde(), cfg(), self.z)
        self.assertEqual(len(self.nep.posts), 1)
        echte = next(iter(self.nep.posts.values()))
        v = self.voorstel()
        self.assertNotIn("01", [p["id"] for p in v["posts"]], "01 staat al bij Zernio en komt niet opnieuw in het voorstel")
        self.assertEqual(v["al_ingepland"], [echte["_id"]])
        self.assertEqual(datetime.fromisoformat(self.boek()["01"]["tijd"]), datetime.fromisoformat(echte["scheduledFor"].replace("Z", "+00:00")))
        with redirect_stdout(io.StringIO()) as uit:
            pr.toon_voorstel(v, self.ronde(), {"posts": self.boek()})
        self.assertIn("Al bij Zernio uit deze ronde (1)", uit.getvalue())
        self.assertIn("Van dit voorstel is nog niets ingepland", uit.getvalue())
        self.echt()
        self.assertEqual(len(self.nep.posts), 3)
        self.assertEqual(eerste["posts"][0]["tijd"], self.boek()["01"]["tijd"])

    def test_3_verder_na_een_storing_halverwege_hetzelfde_voorstel(self):
        self.voorstel()
        echt_plannen, keer = self.z.plan_post, []

        def soms(**kw):
            keer.append(1)
            if len(keer) == 2:
                raise ZernioFout("storing", status=500, tijdelijk=True)
            return echt_plannen(**kw)
        with mock.patch.object(self.z, "plan_post", soms), self.assertRaises(ZernioFout), redirect_stdout(io.StringIO()):
            pr.echt(self.map_, self.ronde(), cfg(), self.z)
        self.assertEqual(len(self.nep.posts), 1)
        uit = self.echt()
        self.assertIn("2 reels ingepland", uit)
        self.assertEqual(len(self.nep.posts), 3)

    def test_4_een_veranderde_caption_of_reel_na_het_voorstel_houdt_echt_tegen(self):
        self.voorstel()
        self.posts[1]["caption"] = "Andere caption"
        schrijf_ronde(self.map_, self.posts)
        with self.assertRaisesRegex(PlanFout, "verouderd"):
            pr.echt(self.map_, self.ronde(), cfg(), self.z)
        self.posts[1]["caption"] = "Caption 2"
        self.posts[2]["tekst"] = "Nieuwe hook"
        schrijf_ronde(self.map_, self.posts)
        with self.assertRaisesRegex(PlanFout, "verouderd"):
            pr.echt(self.map_, self.ronde(), cfg(), self.z)
        with self.assertRaisesRegex(PlanFout, "03"):
            self.voorstel()
        self.assertEqual(len(self.nep.posts), 0)

    def test_13_andere_postregels_na_het_voorstel_houden_echt_tegen(self):
        self.voorstel()
        c = cfg()
        c["posten"]["per_dag"] = 2
        with self.assertRaisesRegex(PlanFout, "postregels"):
            pr.echt(self.map_, self.ronde(), c, self.z)

    def test_5_stand_gaat_door_als_een_reel_in_zernio_gestopt_is(self):
        self.voorstel()
        self.echt()
        weg = self.boek()["02"]["zernio_id"]
        self.assertEqual(self.z.roep("DELETE", f"/posts/{weg}")[0], 200)
        with redirect_stdout(io.StringIO()) as uit:
            pr.stand(self.map_, self.ronde(), cfg(), self.z)
        self.assertIn("2 gepland", uit.getvalue())
        self.assertIn("1 niet meer bij Zernio", uit.getvalue())

    def test_8_een_mislukte_publicatie_heet_niet_ingepland(self):
        self.voorstel()
        mislukt = {"_id": "m" * 24, "status": "failed", "scheduledFor": "2026-10-19T10:00:00.000Z",
                   "platforms": [{"platform": "instagram", "accountId": {"_id": "a" * 24}, "status": "failed", "errorMessage": "Video te kort"}]}
        with mock.patch.object(self.z, "plan_post", return_value=(207, mislukt)):
            uit = self.echt()
        self.assertIn("MISLUKT", uit)
        self.assertIn("Video te kort", uit)
        self.assertIn("0 reels ingepland", uit)

    def test_8_zernio_publiceert_een_tijd_in_het_verleden_meteen(self):
        verleden = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        url = self.z.upload(self.map_ / "klaar" / "01.mp4")
        status, post = self.z.plan_post(account_id="a" * 24, video_url=url, caption="x", tijd=verleden, tijdzone="Europe/Amsterdam",
                                        trial=True, doorzetten="zelf", sleutel="verleden")
        self.assertEqual((status, post["status"]), (201, "published"))
        self.nep.publiceer_faalt = True
        status, post = self.z.plan_post(account_id="a" * 24, video_url=url, caption="y", tijd=verleden, tijdzone="Europe/Amsterdam",
                                        trial=True, doorzetten="zelf", sleutel="verleden-2")
        self.assertEqual((status, post["status"]), (207, "failed"))

    def test_8_bezig_en_traag_worden_opnieuw_geprobeerd(self):
        self.nep.storing = [(r"GET /api/v1/accounts", "bezig")]
        self.assertEqual(len(self.z.accounts()), 1)
        self.nep.storing = [(r"GET /api/v1/accounts", ("traag", 1.5))]
        self.assertEqual(self.z.roep("GET", "/accounts", timeout=0.5)[0], 200, "na een time-out (socket.timeout in 3.9) opnieuw")

    def test_8_een_account_dat_niet_mag_posten_wordt_vooraf_genoemd(self):
        self.nep.accounts[0]["enabled"] = False
        with self.assertRaisesRegex(PlanFout, "aangezet"):
            self.voorstel()

    def test_14_eigen_posts_van_de_klant_tellen_mee(self):
        v = self.voorstel()
        eerste = datetime.fromisoformat(v["posts"][0]["tijd"])
        (self.map_ / "voorstel.json").rename(self.map_ / "voorstel-oud.json")
        self.nep.posts["k" * 24] = {"_id": "k" * 24, "status": "scheduled", "tags": [],
                                    "scheduledFor": eerste.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                                    "platforms": [{"platform": "instagram", "accountId": {"_id": "a" * 24}, "status": "pending"}]}
        v2 = self.voorstel()
        alle = sorted([eerste] + [datetime.fromisoformat(p["tijd"]) for p in v2["posts"]])
        self.assertTrue(all(b - a >= timedelta(minutes=45) for a, b in zip(alle, alle[1:])))


class TestRest(unittest.TestCase):
    def test_15_twee_keer_bewaren_in_dezelfde_seconde_overschrijft_niets(self):
        pad = TMP / "cfg15" / "config.json"
        ins.schrijf({"tekst": {"font": "Anton-Regular.ttf"}}, pad)
        ins.schrijf({"tekst": {"grootte": "groot"}}, pad)
        ins.schrijf({"posten": {"per_dag": 4}}, pad)
        oud = sorted((pad.parent / "oud").glob("config-*.json"))
        self.assertEqual(len(oud), 2)
        self.assertEqual({json.loads(p.read_text())["tekst"]["grootte"] for p in oud}, {"normaal", "groot"})

    def test_17_een_algemene_zernio_sleutel_op_de_mac_telt_niet(self):
        bestand = TMP / "sleutel17" / "zernio-api-key"
        bestand.parent.mkdir(parents=True, exist_ok=True)
        bestand.write_text(SLEUTEL + "\n")
        with mock.patch.object(zmod, "SLEUTELBESTAND", bestand), mock.patch.dict(os.environ, {"ZERNIO_API_KEY": "sk_" + "b" * 64}):
            self.assertEqual(zmod.lees_sleutel(), SLEUTEL)
        with mock.patch.object(zmod, "SLEUTELBESTAND", TMP / "bestaat-niet"), mock.patch.dict(os.environ, {"ZERNIO_API_KEY": "sk_" + "b" * 64}):
            os.environ.pop("TRS_ZERNIO_API_KEY", None)
            with self.assertRaisesRegex(ZernioFout, "nog geen Zernio-sleutel"):
                zmod.lees_sleutel()

    def test_18_winner_bij_een_mediaan_van_0_en_per_soort(self):
        nu = datetime(2026, 11, 20, tzinfo=timezone.utc)
        oud = nu - timedelta(hours=72)
        reels = [{"account": "A", "soort": "trial", "rijp": True, "views": v, "gepost": oud} for v in (0, 0, 0, 2400)]
        reels += [{"account": "A", "soort": "gewoon", "rijp": True, "views": v, "gepost": oud} for v in (5000, 5200, 4800)]
        medianen = cijfers.beoordeel(reels, {"factor": 3, "min_views": 500})
        self.assertEqual(medianen[("A", "trial")], 0)
        self.assertTrue(reels[3]["winner"], "2400 views op een account waar de rest 0 haalt, is een winner")
        self.assertFalse(any(r["winner"] for r in reels[4:]), "gewone reels worden met gewone reels vergeleken")

    def test_20_een_account_erbij_laat_de_andere_staan(self):
        nep = NepZernio()
        try:
            nep.accounts = [{"_id": c * 24, "platform": "instagram", "profileId": "p" * 24, "username": n, "isActive": True}
                            for c, n in (("a", "eerste"), ("b", "tweede"))]
            z = Zernio(sleutel=SLEUTEL, basis=nep.basis, pauze=0, slaap=lambda s: None)
            with redirect_stdout(io.StringIO()):
                koppel.gebruik(z, ["eerste"])
                koppel.gebruik(z, ["tweede"], erbij=True)
            self.assertEqual([a["gebruikersnaam"] for a in koppel.in_gebruik()], ["eerste", "tweede"])
        finally:
            nep.stop()

    def test_21_lettertypes_te_zien(self):
        r = draai("instellingen.py", "--lettertypes")
        self.assertIn('"font": "Poppins-ExtraBold.ttf"', r.stdout)
        self.assertEqual(r.stdout.count("\n"), len(ins.FONTS))


if __name__ == "__main__":
    unittest.main()
