import json
import unittest

import basis  # noqa: F401  (zet de tijdelijke mappen voordat de scripts laden)
import instellingen as ins


def standaard():
    return json.loads(ins.STANDAARD.read_text(encoding="utf-8"))


class TestInstellingen(unittest.TestCase):
    def test_standaard_is_geldig(self):
        cfg = ins.keur(standaard())
        self.assertEqual(cfg["tekst"]["font"], "Poppins-ExtraBold.ttf")
        self.assertTrue((ins.FONTMAP / cfg["tekst"]["font"]).exists())

    def test_elk_lettertype_staat_in_de_map(self):
        for bestand in ins.FONTS:
            self.assertTrue((ins.FONTMAP / bestand).exists(), bestand)

    def test_foute_waarden_worden_geweigerd(self):
        fout = [
            ("tekst", "font", "Comic.ttf"), ("tekst", "vorm", "wolk"), ("tekst", "kleur_tekst", "rood"),
            ("tekst", "kleur_vlak", "#FFF"), ("tekst", "grootte", "enorm"), ("tekst", "positie", "links"),
            ("tekst", "hoofdletters", "ja"), ("posten", "per_dag", 0), ("posten", "per_dag", 21),
            ("posten", "per_dag", True), ("posten", "per_dag", 5.0), ("posten", "minuten_tussen", 29),
            ("posten", "van", 24), ("posten", "tot", 25), ("posten", "tijdzone", "Mars/Olympus"),
            ("posten", "tijdzone", "UTC"), ("posten", "tijdzone", "US/Pacific"), ("posten", "tijdzone", "Etc/Unknown"),
            ("posten", "tijdzone", "SystemV/AST4"), ("posten", "doorzetten", "nooit"), ("winners", "factor", 1),
            ("winners", "min_views", -1),
        ]
        for blok, veld, waarde in fout:
            cfg = standaard()
            cfg[blok][veld] = waarde
            with self.assertRaises(ins.InstellingFout, msg=f"{blok}.{veld}={waarde!r}"):
                ins.keur(cfg)

    def test_venster_moet_kloppen(self):
        cfg = standaard()
        cfg["posten"].update(van=12, tot=12)
        with self.assertRaises(ins.InstellingFout):
            ins.keur(cfg)
        cfg["posten"].update(van=12, tot=13, minuten_tussen=90)
        with self.assertRaises(ins.InstellingFout):
            ins.keur(cfg)
        cfg["posten"].update(van=0, tot=24, minuten_tussen=240)
        ins.keur(cfg)

    def test_schrijven_voegt_per_veld_samen_en_bewaart_de_oude(self):
        pad = basis.TMP / "cfg-test" / "config.json"
        ins.schrijf({"tekst": {"font": "Anton-Regular.ttf"}}, pad)
        cfg = ins.schrijf({"posten": {"per_dag": 12}}, pad)
        self.assertEqual(cfg["tekst"]["font"], "Anton-Regular.ttf")
        self.assertEqual(cfg["posten"]["per_dag"], 12)
        self.assertEqual(cfg["posten"]["minuten_tussen"], 45)
        self.assertEqual(len(list((pad.parent / "oud").glob("config-*.json"))), 1)
        with self.assertRaises(ins.InstellingFout):
            ins.schrijf({"posten": {"per_dag": 99}}, pad)
        self.assertEqual(ins.laad(pad)["posten"]["per_dag"], 12)

    def test_een_kapotte_oude_config_houdt_een_goed_blok_niet_tegen(self):
        pad = basis.TMP / "cfg-kapot" / "config.json"
        pad.parent.mkdir(parents=True, exist_ok=True)
        pad.write_text('{"tekst": {"font": "Comic.ttf"}}')
        cfg = ins.schrijf(json.loads(ins.STANDAARD.read_text(encoding="utf-8")), pad)
        self.assertEqual(cfg["tekst"]["font"], "Poppins-ExtraBold.ttf")
        self.assertEqual(len(list((pad.parent / "oud").glob("config-*.json"))), 1, "de kapotte blijft bewaard")

    def test_in_woorden_noemt_wat_er_echt_past(self):
        cfg = ins.keur(json.loads(ins.STANDAARD.read_text(encoding="utf-8")))
        cfg["posten"].update(per_dag=20, minuten_tussen=45, van=9, tot=21)
        self.assertIn("in dat venster passen er 16 per dag", ins.in_woorden(cfg))
        self.assertEqual(ins.per_dag_echt(cfg["posten"]), 16)

    def test_in_woorden(self):
        tekst = ins.in_woorden(ins.keur(standaard()))
        self.assertIn("Poppins ExtraBold", tekst)
        self.assertIn("hooguit 5 per account per dag", tekst)


if __name__ == "__main__":
    unittest.main()
