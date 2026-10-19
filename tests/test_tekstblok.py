import json
import unittest

import basis  # noqa: F401
import instellingen as ins
from tekstblok import BOVEN_Y, CANVAS, ONDER_Y, TekstFout, render


def cfg(**tekst):
    c = ins.keur(json.loads(ins.STANDAARD.read_text(encoding="utf-8")))
    c["tekst"].update(tekst)
    return c


def zichtbaar(plaat):
    """Het vak waar iets getekend is (alfa boven nul)."""
    return plaat.getchannel("A").getbbox()


class TestTekstblok(unittest.TestCase):
    def test_blokje_heeft_de_gekozen_kleuren(self):
        p = render("Hallo wereld", cfg(kleur_tekst="#112233", kleur_vlak="#E1306C"))
        self.assertEqual(p.size, CANVAS)
        kleuren = {k[:3] for _, k in p.getcolors(1 << 20) if k[3] == 255}
        self.assertIn((0xE1, 0x30, 0x6C), kleuren)
        self.assertIn((0x11, 0x22, 0x33), kleuren)

    def test_rand_heeft_geen_blok(self):
        p = render("Hallo wereld", cfg(vorm="rand", kleur_tekst="#FFE500", kleur_vlak="#000000"))
        kleuren = {k[:3] for _, k in p.getcolors(1 << 20) if k[3] == 255}
        self.assertIn((0xFF, 0xE5, 0x00), kleuren)
        self.assertIn((0, 0, 0), kleuren)
        # Een blokje vult ook de ruimte tussen en rond de letters; losse letters met een rand niet
        vol = lambda plaat: sum(1 for a in plaat.getchannel("A").getdata() if a == 255)
        blok = render("Hallo wereld", cfg(kleur_tekst="#FFE500", kleur_vlak="#000000"))
        self.assertLess(vol(p), vol(blok) * 0.8)
        x0, y0, x1, y1 = zichtbaar(p)
        self.assertEqual(p.getpixel((x0 + 1, y0 + 1))[3], 0, "de hoek van het vak is leeg bij losse letters")

    def test_plek_in_beeld(self):
        for positie in ("boven", "midden", "onder"):
            for vorm in ("blokje", "rand"):
                x0, y0, x1, y1 = zichtbaar(render("Twee regels\nin beeld", cfg(positie=positie, vorm=vorm)))
                self.assertGreaterEqual(y0, BOVEN_Y - 2, (positie, vorm))
                self.assertLessEqual(y1, ONDER_Y + 2, (positie, vorm))
                self.assertGreaterEqual(x0, 100)
                self.assertLessEqual(x1, CANVAS[0] - 100)
        boven = zichtbaar(render("Tekst", cfg(positie="boven")))[1]
        midden = zichtbaar(render("Tekst", cfg(positie="midden")))[1]
        onder = zichtbaar(render("Tekst", cfg(positie="onder")))[1]
        self.assertLess(boven, midden)
        self.assertLess(midden, onder)

    def test_groter_is_groter(self):
        hoogte = lambda g: (lambda b: b[3] - b[1])(zichtbaar(render("Tekst", cfg(grootte=g))))
        self.assertLess(hoogte("klein"), hoogte("normaal"))
        self.assertLess(hoogte("normaal"), hoogte("groot"))

    def test_hoofdletters(self):
        self.assertEqual(render("tekst", cfg(hoofdletters=True)).tobytes(), render("TEKST", cfg()).tobytes())

    def test_lange_tekst_breekt_af_binnen_de_breedte(self):
        x0, _, x1, _ = zichtbaar(render("Dit is een behoorlijk lange zin die over meerdere regels moet lopen", cfg()))
        self.assertLessEqual(x1 - x0, 860)

    def test_te_lang_geeft_een_fout(self):
        with self.assertRaises(TekstFout):
            render(" ".join(["woord"] * 80), cfg())
        with self.assertRaises(TekstFout):
            render("Superlangwoordzonderspatiesdatnergensinpastnietopdezeregel", cfg(vorm="rand", grootte="groot"))

    def test_ontbrekend_teken_geeft_een_fout(self):
        with self.assertRaisesRegex(TekstFout, "\u4e2d"):
            render("Midden \u4e2d", cfg())

    def test_emoji_wordt_in_kleur_gezet(self):
        p = render("Kijk hier 👇", cfg(kleur_tekst="#000000", kleur_vlak="#FFFFFF"))
        gekleurd = [k for _, k in p.getcolors(1 << 20) if k[3] == 255 and len({k[0], k[1], k[2]}) > 1 and max(k[:3]) - min(k[:3]) > 60]
        self.assertTrue(gekleurd, "het emoji-handje hoort in kleur te staan")

    def test_lege_tekst(self):
        with self.assertRaises(TekstFout):
            render("   ", cfg())

    def test_elk_lettertype_rendert(self):
        for font in ins.FONTS:
            for vorm in ("blokje", "rand"):
                self.assertIsNotNone(zichtbaar(render("Reels die werken 2026!", cfg(font=font, vorm=vorm))), (font, vorm))


if __name__ == "__main__":
    unittest.main()
