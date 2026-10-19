import os
import stat
import subprocess
import sys
import unittest

import basis
from nep_zernio import SLEUTEL, NepZernio

SCRIPT = str(basis.REPO / "engine" / "scripts" / "sleutel.py")


class TestSleutel(unittest.TestCase):
    def setUp(self):
        self.nep = NepZernio()
        self.thuis = basis.TMP / f"thuis-{self.id().split('.')[-1]}"
        self.bestand = self.thuis / ".config" / "trial-reels-starter" / "zernio-api-key"

    def tearDown(self):
        self.nep.stop()

    def bewaar(self, sleutel):
        # Een eigen HOME, zodat de echte map van de gebruiker nooit geraakt wordt
        env = {**os.environ, "HOME": str(self.thuis), "TRS_ZERNIO_BASIS": self.nep.basis}
        return subprocess.run([sys.executable, SCRIPT], input=sleutel, capture_output=True, text=True, env=env)

    def test_verkeerde_vorm(self):
        r = self.bewaar("hallo")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("geen Zernio-sleutel", r.stderr)
        self.assertFalse(self.bestand.exists())
        self.assertEqual(self.nep.aanroepen, [], "een sleutel in de verkeerde vorm gaat niet naar Zernio")

    def test_sleutel_die_zernio_niet_kent(self):
        r = self.bewaar("sk_" + "0" * 64)
        self.assertIn("neemt deze sleutel niet aan", r.stderr)
        self.assertFalse(self.bestand.exists())

    def test_goede_sleutel_alleen_voor_jou_en_de_oude_blijft(self):
        r = self.bewaar(SLEUTEL + "\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn(SLEUTEL, r.stdout + r.stderr, "de sleutel komt nooit in beeld")
        self.assertEqual(self.bestand.read_text().strip(), SLEUTEL)
        self.assertEqual(stat.S_IMODE(self.bestand.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.bestand.parent.stat().st_mode), 0o700)
        self.assertEqual(self.bewaar(SLEUTEL).returncode, 0)
        self.assertEqual(len(list(self.bestand.parent.glob("zernio-api-key.oud-*"))), 1)


if __name__ == "__main__":
    unittest.main()
