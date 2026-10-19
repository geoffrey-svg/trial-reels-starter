import io
import json
import shutil
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone

import basis
import instellingen as ins
import plan_ronde as pr
from maak_reels import lees_ronde, vingerafdruk
from nep_zernio import SLEUTEL, NepZernio
from planning import PlanFout
from zernio import TAG, Zernio, ZernioFout

TMP = basis.TMP / "flow"


def cfg():
    return ins.keur(json.loads(ins.STANDAARD.read_text(encoding="utf-8")))


def maak_klaar(map_, post):
    """Een gemaakte reel zoals maak_reels hem achterlaat: het bestand plus waarvan hij gemaakt is."""
    (map_ / "klaar" / f"{post['id']}.mp4").write_bytes(b"\0" * 1000 + post["id"].encode())
    (map_ / "klaar" / f"{post['id']}.json").write_text(json.dumps(vingerafdruk(post, cfg())), encoding="utf-8")


def account(_id, naam, volgers=500, **extra):
    return {"_id": _id, "platform": "instagram", "profileId": {"_id": "p" * 24}, "username": naam,
            "isActive": True, "followersCount": volgers, **extra}


class TestZernioFlow(unittest.TestCase):
    def setUp(self):
        self.nep = NepZernio()
        self.z = Zernio(sleutel=SLEUTEL, basis=self.nep.basis, pauze=0, slaap=lambda s: None)
        self.nep.accounts = [account("a" * 24, "groot_account", 1500), account("b" * 24, "klein_account", 40)]
        if TMP.exists():
            shutil.rmtree(TMP)
        self.map_ = TMP / "ronde1"
        (self.map_ / "klaar").mkdir(parents=True)
        posts = []
        for i in range(1, 5):
            post = {"id": f"0{i}", "video": f"klaar/0{i}.mp4", "tekst": f"Tekst {i}", "caption": f"Caption {i} #reels"}
            maak_klaar(self.map_, post)
            posts.append(post)
        (self.map_ / "ronde.json").write_text(json.dumps({"naam": "ronde1", "posts": posts}), encoding="utf-8")
        self.ronde = lees_ronde(self.map_)
        ins.MIJN.mkdir(parents=True, exist_ok=True)
        pr.ACCOUNTS.write_text(json.dumps([{"id": "a" * 24, "gebruikersnaam": "groot_account"}]), encoding="utf-8")

    def tearDown(self):
        self.nep.stop()

    def voorstel(self, soort="auto"):
        with redirect_stdout(io.StringIO()):
            v = pr.voorstel(self.map_, self.ronde, cfg(), self.z, soort, None)
        pr.schrijf_json(self.map_ / "voorstel.json", v)
        return v

    def echt(self):
        with redirect_stdout(io.StringIO()) as uit:
            pr.echt(self.map_, self.ronde, cfg(), self.z)
        return uit.getvalue()

    def boek(self):
        return json.loads((self.map_ / "ingepland.json").read_text(encoding="utf-8"))["posts"]

    def test_voorstel_verandert_niets_bij_zernio(self):
        v = self.voorstel()
        self.assertEqual(len(v["posts"]), 4)
        self.assertEqual(self.nep.tel("POST", r"/posts$"), 0)
        self.assertEqual(self.nep.tel("POST", r"/media/presign"), 0)
        self.assertFalse((self.map_ / "ingepland.json").exists())

    def test_echt_plant_precies_het_voorstel_als_trial_reel(self):
        v = self.voorstel()
        self.echt()
        posts = list(self.nep.posts.values())
        self.assertEqual(len(posts), 4)
        self.assertEqual(len(self.nep.uploads), 4)
        for p, verwacht in zip(sorted(posts, key=lambda p: p["scheduledFor"]), v["posts"]):
            self.assertEqual(datetime.fromisoformat(p["scheduledFor"].replace("Z", "+00:00")),
                             datetime.fromisoformat(verwacht["tijd"]))
            self.assertEqual(p["platforms"][0]["accountId"]["_id"], "a" * 24)
            self.assertTrue(p["platforms"][0]["isTrialReel"])
            self.assertEqual(p["platforms"][0]["trialGraduationStrategy"], "MANUAL")
            self.assertIn(TAG, p["tags"])
            self.assertEqual(p["timezone"], "Europe/Amsterdam")
        self.assertEqual(sorted(p["content"] for p in posts), [f"Caption {i} #reels" for i in range(1, 5)])
        self.assertTrue(all(r.get("zernio_id") for r in self.boek().values()))

    def test_automatisch_doorzetten(self):
        c = cfg()
        c["posten"]["doorzetten"] = "automatisch"
        v = pr.voorstel(self.map_, self.ronde, c, self.z, "auto", None)
        pr.schrijf_json(self.map_ / "voorstel.json", v)
        with redirect_stdout(io.StringIO()):
            pr.echt(self.map_, self.ronde, c, self.z)
        self.assertEqual({p["platforms"][0]["trialGraduationStrategy"] for p in self.nep.posts.values()}, {"SS_PERFORMANCE"})

    def test_minder_dan_200_volgers_wordt_gewone_reel(self):
        pr.ACCOUNTS.write_text(json.dumps([{"id": "b" * 24, "gebruikersnaam": "klein_account"}]), encoding="utf-8")
        with self.assertRaisesRegex(PlanFout, "200"):
            self.voorstel("trial")
        v = self.voorstel()
        self.assertEqual({p["soort"] for p in v["posts"]}, {"gewoon"})
        self.echt()
        self.assertFalse(any(p["platforms"][0].get("isTrialReel") for p in self.nep.posts.values()))

    def test_onbekend_aantal_volgers_vraagt_een_keuze(self):
        self.nep.accounts[0].pop("followersCount")
        with self.assertRaisesRegex(PlanFout, "--soort"):
            self.voorstel()
        self.assertEqual({p["soort"] for p in self.voorstel("trial")["posts"]}, {"trial"})

    def test_om_de_beurt_over_twee_accounts(self):
        pr.ACCOUNTS.write_text(json.dumps([{"id": "a" * 24, "gebruikersnaam": "groot_account"},
                                           {"id": "b" * 24, "gebruikersnaam": "klein_account"}]), encoding="utf-8")
        v = self.voorstel()
        self.assertEqual([p["gebruikersnaam"] for p in v["posts"]], ["groot_account", "klein_account"] * 2)
        self.assertEqual([p["soort"] for p in v["posts"]], ["trial", "gewoon"] * 2)

    def test_twee_keer_echt_plant_niets_dubbel(self):
        self.voorstel()
        self.echt()
        with self.assertRaisesRegex(PlanFout, "al klaar"):
            self.voorstel()
        uit = self.echt()
        self.assertIn("Alles uit dit voorstel staat al klaar", uit)
        self.assertEqual(len(self.nep.posts), 4)

    def test_weggevallen_antwoord_geeft_geen_tweede_post(self):
        self.voorstel()
        self.nep.storing = [(r"POST /api/v1/posts$", "slik")]
        self.echt()
        self.assertEqual(len(self.nep.posts), 4)
        self.assertEqual(self.nep.tel("POST", r"/posts$"), 5)

    def test_stoppen_en_verder_gaan(self):
        self.voorstel()
        # Drie keer geen antwoord op dezelfde post: het script stopt, maar Zernio heeft hem wel
        self.nep.storing = [(r"POST /api/v1/posts$", "slik")] * 3
        with self.assertRaises(ZernioFout), redirect_stdout(io.StringIO()):
            pr.echt(self.map_, self.ronde, cfg(), self.z)
        self.assertEqual(len(self.nep.posts), 1)
        self.assertFalse(self.boek()["01"].get("zernio_id"))
        uploads = len(self.nep.uploads)
        self.echt()
        self.assertEqual(len(self.nep.posts), 4, "de eerste is overgenomen, niet opnieuw gemaakt")
        self.assertEqual(len(self.nep.uploads), uploads + 3, "de video van de eerste is niet opnieuw geüpload")
        self.assertTrue(all(r.get("zernio_id") for r in self.boek().values()))

    def test_storing_bij_zernio_wordt_opnieuw_geprobeerd(self):
        self.voorstel()
        self.nep.storing = [(r"POST /api/v1/posts$", 503), (r"POST /api/v1/media/presign", 429)]
        self.echt()
        self.assertEqual(len(self.nep.posts), 4)

    def test_verouderd_voorstel(self):
        v = self.voorstel()
        v["posts"][0]["tijd"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        pr.schrijf_json(self.map_ / "voorstel.json", v)
        with self.assertRaisesRegex(PlanFout, "verouderd"):
            pr.echt(self.map_, self.ronde, cfg(), self.z)
        self.assertEqual(len(self.nep.posts), 0)

    def test_intussen_iets_anders_ingepland(self):
        v = self.voorstel()
        tijd = datetime.fromisoformat(v["posts"][0]["tijd"])
        self.nep.posts["x" * 24] = {"_id": "x" * 24, "status": "scheduled", "tags": [TAG],
                                    "scheduledFor": (tijd + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                                    "platforms": [{"platform": "instagram", "accountId": {"_id": "a" * 24}, "status": "pending"}]}
        with self.assertRaisesRegex(PlanFout, "intussen"):
            pr.echt(self.map_, self.ronde, cfg(), self.z)
        self.assertEqual(len(self.nep.posts), 1)

    def test_bestaande_posts_tellen_mee_in_het_voorstel(self):
        eerste = self.voorstel()
        self.echt()
        # Een tweede ronde op hetzelfde account komt na de eerste
        tweede = TMP / "ronde2"
        shutil.copytree(self.map_ / "klaar", tweede / "klaar")
        shutil.copy(self.map_ / "ronde.json", tweede / "ronde.json")
        v = pr.voorstel(tweede, lees_ronde(tweede), cfg(), self.z, "auto", None)
        oud = {p["tijd"] for p in eerste["posts"]}
        self.assertFalse(oud & {p["tijd"] for p in v["posts"]})
        alle = sorted(datetime.fromisoformat(t) for t in oud | {p["tijd"] for p in v["posts"]})
        self.assertTrue(all(b - a >= timedelta(minutes=45) for a, b in zip(alle, alle[1:])))

    def test_koppeling_kapot(self):
        self.nep.accounts[0]["needsReconnection"] = True
        with self.assertRaisesRegex(PlanFout, "vernieuwd"):
            self.voorstel()

    def test_reel_nog_niet_gemaakt(self):
        (self.map_ / "klaar" / "03.mp4").unlink()
        with self.assertRaisesRegex(PlanFout, "03"):
            self.voorstel()

    def test_stand_noemt_de_reden_van_mislukken(self):
        self.voorstel()
        self.echt()
        pid = self.boek()["02"]["zernio_id"]
        self.nep.posts[pid]["status"] = "failed"
        self.nep.posts[pid]["platforms"][0].update(status="failed", errorMessage="Video te kort")
        eerste = self.boek()["01"]["zernio_id"]
        self.nep.posts[eerste]["platforms"][0].update(status="published", platformPostUrl="https://instagram.com/reel/x")
        with redirect_stdout(io.StringIO()) as uit:
            pr.stand(self.map_, self.ronde, cfg(), self.z)
        tekst = uit.getvalue()
        self.assertIn("1 mislukt", tekst)
        self.assertIn("1 online", tekst)
        self.assertIn("Video te kort", tekst)
        self.assertEqual(self.boek()["01"]["url"], "https://instagram.com/reel/x")

    def test_foute_sleutel(self):
        z = Zernio(sleutel="sk_" + "0" * 64, basis=self.nep.basis, pauze=0, slaap=lambda s: None)
        with self.assertRaises(ZernioFout) as e:
            z.accounts()
        self.assertEqual(e.exception.status, 401)


if __name__ == "__main__":
    unittest.main()
