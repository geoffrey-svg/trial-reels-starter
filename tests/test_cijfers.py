import json
import shutil
import unittest
from datetime import datetime, timedelta, timezone

import basis  # noqa: F401
import cijfers
import instellingen as ins
from nep_zernio import SLEUTEL, NepZernio
from zernio import Zernio

NU = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def cfg():
    return ins.keur(json.loads(ins.STANDAARD.read_text(encoding="utf-8")))


def analytics(zid, uren_oud, views, bereik=None, angle_post=None):
    return {"_id": "ext" + zid, "latePostId": zid, "publishedAt": (NU - timedelta(hours=uren_oud)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "platformPostUrl": f"https://www.instagram.com/reel/{zid}/", "status": "published",
            "analytics": {"views": views, "reach": views if bereik is None else bereik, "likes": 1, "comments": 0,
                          "shares": 2, "saves": 3, "igReelsAvgWatchTime": 4000}}


class TestCijfers(unittest.TestCase):
    def setUp(self):
        rondes = ins.MIJN / "rondes"
        if rondes.exists():
            shutil.rmtree(rondes)
        self.nep = NepZernio()
        self.z = Zernio(sleutel=SLEUTEL, basis=self.nep.basis, pauze=0, slaap=lambda s: None)

    def tearDown(self):
        self.nep.stop()

    def ronde(self, naam, posts):
        m = ins.MIJN / "rondes" / naam
        m.mkdir(parents=True)
        (m / "ronde.json").write_text(json.dumps({"naam": naam, "posts": [
            {"id": pid, "video": "x.mp4", "tekst": f"Tekst {pid}", "caption": "c", "angle": angle} for pid, _, _, angle in posts]}))
        (m / "ingepland.json").write_text(json.dumps({"posts": {
            pid: {"zernio_id": zid, "account": acc, "gebruikersnaam": acc + "_naam", "soort": "trial"} for pid, zid, acc, _ in posts}}))

    def test_winner_is_keer_de_mediaan_van_het_eigen_account(self):
        # Account A: views 100, 120, 130, 900 -> mediaan 125, 900 is 7,2 keer. Account B: alles rond 5000.
        self.ronde("r1", [("1", "z1", "A", "pijn"), ("2", "z2", "A", "pijn"), ("3", "z3", "A", "droom"), ("4", "z4", "A", "droom"),
                          ("5", "z5", "B", "pijn"), ("6", "z6", "B", "pijn"), ("7", "z7", "B", "droom"), ("8", "z8", "A", "droom")])
        self.nep.cijfers = {
            "A": [analytics("z1", 72, 100), analytics("z2", 72, 120), analytics("z3", 72, 130), analytics("z4", 72, 900),
                  analytics("z8", 10, 5000), analytics("vreemd", 72, 99999)],
            "B": [analytics("z5", 72, 5000), analytics("z6", 72, 5200), analytics("z7", 72, 4900)],
        }
        reels = cijfers.verzamel(self.z, cijfers.ingepland(), 30, NU)
        self.assertEqual(len(reels), 8, "een post die niet van deze starter is, telt niet mee")
        medianen = cijfers.beoordeel(reels, cfg()["winners"])
        self.assertEqual(medianen[("A", "trial")], 125)
        winners = {r["id"] for r in reels if r["winner"]}
        self.assertEqual(winners, {"4"}, "jonger dan 48 uur telt niet, en B haalt nergens 3 keer zijn mediaan")
        jong = next(r for r in reels if r["id"] == "8")
        self.assertIsNone(jong["keer"])
        tekst = cijfers.verslag(reels, medianen, cfg(), NU)
        self.assertIn("## Winners (1)", tekst)
        self.assertIn("7.2x", tekst)
        self.assertIn("| droom |", tekst)
        self.assertIn("nog niet", tekst)

    def test_minimum_aantal_views(self):
        self.ronde("r2", [("1", "y1", "A", ""), ("2", "y2", "A", ""), ("3", "y3", "A", "")])
        self.nep.cijfers = {"A": [analytics("y1", 72, 10), analytics("y2", 72, 10), analytics("y3", 72, 400)]}
        reels = cijfers.verzamel(self.z, cijfers.ingepland(), 30, NU)
        cijfers.beoordeel(reels, cfg()["winners"])
        self.assertFalse(any(r["winner"] for r in reels), "400 views is 40 keer de mediaan maar onder de 500")

    def test_account_zonder_bereik_krijgt_een_waarschuwing(self):
        self.ronde("r3", [(str(i), f"s{i}", "A", "") for i in range(6)])
        self.nep.cijfers = {"A": [analytics(f"s{i}", 72, 0, bereik=0) for i in range(6)]}
        reels = cijfers.verzamel(self.z, cijfers.ingepland(), 30, NU)
        tekst = cijfers.verslag(reels, cijfers.beoordeel(reels, cfg()["winners"]), cfg(), NU)
        self.assertIn("0 views en 0 bereik", tekst)

    def test_lege_cijfers_zijn_geen_nul(self):
        self.ronde("r4", [("1", "n1", "A", "")])
        post = analytics("n1", 72, 0)
        post["analytics"]["views"] = None
        self.nep.cijfers = {"A": [post]}
        reels = cijfers.verzamel(self.z, cijfers.ingepland(), 30, NU)
        cijfers.beoordeel(reels, cfg()["winners"])
        self.assertIsNone(reels[0]["keer"])
        self.assertIn("| - |", cijfers.verslag(reels, {}, cfg(), NU))


if __name__ == "__main__":
    unittest.main()
