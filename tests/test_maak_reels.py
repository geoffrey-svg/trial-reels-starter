import json
import shutil
import unittest
from pathlib import Path

import basis
import instellingen as ins
from maak_reels import RondeFout, controleer, lees_ronde, maak_een, meet

TMP = basis.TMP / "reels"


def cfg():
    return ins.keur(json.loads(ins.STANDAARD.read_text(encoding="utf-8")))


def ronde(map_, posts):
    map_.mkdir(parents=True, exist_ok=True)
    (map_ / "ronde.json").write_text(json.dumps({"naam": map_.name, "posts": posts}), encoding="utf-8")
    return lees_ronde(map_)


class TestMaakReels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TMP.mkdir(parents=True, exist_ok=True)
        basis.maak_video(TMP / "liggend.mp4", 1920, 1080, 5)
        basis.maak_video(TMP / "staand.mp4", 1080, 1920, 4, geluid=False)
        basis.maak_video(TMP / "lang.mp4", 640, 360, 95, geluid=False)
        basis.maak_video(TMP / "kort.mp4", 640, 360, 2, geluid=False)
        basis.maak_video(TMP / "plat.mp4", 1920, 1080, 4)
        # Zoals een telefoon filmt: liggend opgeslagen, met een kenmerk dat hij gedraaid getoond moet worden
        import subprocess
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-display_rotation:v:0", "90",
                        "-i", str(TMP / "plat.mp4"), "-c", "copy", str(TMP / "gedraaid.mp4")], check=True)
        basis.maak_video(TMP / "hdr.mp4", 1080, 1920, 4, geluid=False,
                         extra=["-vf", "setparams=color_primaries=bt2020:color_trc=arib-std-b67:colorspace=bt2020nc"])

    def map_(self, naam):
        m = TMP / naam
        if m.exists():
            shutil.rmtree(m)
        return m

    def test_liggend_met_tekst_en_geluid(self):
        m = self.map_("r1")
        r = ronde(m, [{"id": "01", "video": str(TMP / "liggend.mp4"), "tekst": "Hallo 👇", "caption": "x"}])
        maak_een(m, r["posts"][0], meet(TMP / "liggend.mp4"), cfg())
        na = meet(m / "klaar" / "01.mp4")
        self.assertEqual((na["breedte"], na["hoogte"]), (1080, 1920))
        self.assertAlmostEqual(na["duur"], 5, delta=0.1)
        self.assertTrue(na["geluid"])
        self.assertTrue((m / "klaar" / "01.jpg").exists())
        self.assertFalse(list((m / "klaar").glob(".*tekst.png")), "het hulpbestand blijft niet staan")

    def test_staand_zonder_tekst_krijgt_stil_geluid(self):
        m = self.map_("r2")
        r = ronde(m, [{"id": "a", "video": "../staand.mp4"}])
        maak_een(m, r["posts"][0], meet(TMP / "staand.mp4"), cfg())
        na = meet(m / "klaar" / "a.mp4")
        self.assertTrue(na["geluid"])
        self.assertAlmostEqual(na["duur"], 4, delta=0.1)

    def test_gedraaide_video_telt_als_staand(self):
        m = meet(TMP / "gedraaid.mp4")
        self.assertLess(m["breedte"], m["hoogte"])

    def test_hdr_wordt_gewone_kleuren(self):
        m = self.map_("r3")
        r = ronde(m, [{"id": "h", "video": str(TMP / "hdr.mp4"), "tekst": "HDR"}])
        info = meet(TMP / "hdr.mp4")
        self.assertTrue(info["hdr"])
        maak_een(m, r["posts"][0], info, cfg())
        import subprocess
        uit = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=color_transfer",
                              "-of", "csv=p=0", str(m / "klaar" / "h.mp4")], capture_output=True, text=True).stdout.strip()
        self.assertEqual(uit, "bt709")

    def test_knippen_met_van_en_tot(self):
        m = self.map_("r4")
        r = ronde(m, [{"id": "k", "video": str(TMP / "lang.mp4"), "van": 10, "tot": 18.5}])
        maak_een(m, r["posts"][0], meet(TMP / "lang.mp4"), cfg())
        self.assertAlmostEqual(meet(m / "klaar" / "k.mp4")["duur"], 8.5, delta=0.1)

    def test_te_lang_te_kort_en_tot_na_het_einde(self):
        m = self.map_("r5")
        for post in ({"id": "l", "video": str(TMP / "lang.mp4")}, {"id": "k", "video": str(TMP / "kort.mp4")},
                     {"id": "t", "video": str(TMP / "staand.mp4"), "van": 0, "tot": 9}):
            r = ronde(m, [post])
            with self.assertRaises(RondeFout, msg=post["id"]):
                controleer(m, r["posts"], cfg())

    def test_controleer_vangt_tekst_die_niet_past(self):
        m = self.map_("r6")
        r = ronde(m, [{"id": "x", "video": str(TMP / "staand.mp4"), "tekst": "woord " * 80}])
        with self.assertRaisesRegex(RondeFout, "post x"):
            controleer(m, r["posts"], cfg())

    def test_ronde_fouten(self):
        m = self.map_("r7")
        foute = [
            [{"id": "a", "video": str(TMP / "staand.mp4")}, {"id": "a", "video": str(TMP / "staand.mp4")}],
            [{"id": "a b", "video": str(TMP / "staand.mp4")}],
            [{"id": "a", "video": str(TMP / "bestaat-niet.mp4")}],
            [{"id": "a", "video": str(TMP / "staand.mp4"), "caption": "x" * 2201}],
            [{"id": "a", "video": str(TMP / "staand.mp4"), "van": True}],
            [],
        ]
        for posts in foute:
            with self.assertRaises(RondeFout, msg=str(posts)[:80]):
                ronde(m, posts)

    def test_nooit_overschrijven_en_opnieuw_bewaart_de_oude(self):
        import subprocess
        import sys
        m = self.map_("r8")
        ronde(m, [{"id": "01", "video": str(TMP / "staand.mp4"), "tekst": "Eerste"}])
        script = str(basis.REPO / "engine" / "scripts" / "maak_reels.py")
        subprocess.run([sys.executable, script, str(m)], check=True, capture_output=True)
        eerst = (m / "klaar" / "01.mp4").stat().st_mtime_ns
        uit = subprocess.run([sys.executable, script, str(m)], check=True, capture_output=True, text=True).stdout
        self.assertIn("1 stonden er al", uit)
        self.assertEqual((m / "klaar" / "01.mp4").stat().st_mtime_ns, eerst)
        subprocess.run([sys.executable, script, str(m), "--opnieuw", "01"], check=True, capture_output=True)
        self.assertEqual(len(list((m / "klaar" / "oud").glob("01-*.mp4"))), 1)
        self.assertTrue((m / "klaar" / "01.mp4").exists())
        self.assertTrue((m / "overzicht.md").read_text().count("| 01 | ja |") == 1)


if __name__ == "__main__":
    unittest.main()
