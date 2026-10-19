import unittest
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import basis  # noqa: F401
from planning import PlanFout, dagtijden, past, plan

AMS = ZoneInfo("Europe/Amsterdam")
P = {"per_dag": 5, "minuten_tussen": 45, "van": 9, "tot": 21, "tijdzone": "Europe/Amsterdam"}


def lokaal(t):
    return t.astimezone(AMS).strftime("%d %H:%M")


class TestPlanning(unittest.TestCase):
    def test_dagtijden_gelijk_verspreid(self):
        tijden = [t.strftime("%H:%M") for t in dagtijden(date(2026, 11, 3), P)]
        self.assertEqual(tijden, ["09:00", "11:24", "13:48", "16:12", "18:36"])

    def test_venster_beperkt_het_aantal(self):
        p = {**P, "per_dag": 20, "minuten_tussen": 60, "van": 9, "tot": 12}
        self.assertEqual(len(dagtijden(date(2026, 11, 3), p)), 3)

    def test_wintertijd_houdt_de_klok_vast(self):
        # 25 okt 2026 gaat de klok terug; 9:00 blijft 9:00 op de klok
        zo = [t.strftime("%H:%M %Z") for t in dagtijden(date(2026, 10, 25), P)]
        self.assertEqual(zo[0], "09:00 CET")
        za = dagtijden(date(2026, 10, 24), P)[0]
        self.assertEqual(za.astimezone(timezone.utc).hour, 7)

    def test_om_de_beurt_en_niet_te_vroeg(self):
        nu = datetime(2026, 11, 3, 10, 0, tzinfo=AMS)   # 11:24 is de eerste die na 20 minuten marge vrij is
        r = plan([(str(i), None) for i in range(6)], ["A", "B"], {}, P, nu)
        self.assertEqual([a for _, a, _ in r], ["A", "B"] * 3)
        self.assertEqual(lokaal(r[0][2]), "03 11:24")
        self.assertEqual(lokaal(r[2][2]), "03 13:48")
        self.assertTrue(all(t >= nu + timedelta(minutes=20) for _, _, t in r))

    def test_marge_van_twintig_minuten(self):
        nu = datetime(2026, 11, 3, 11, 5, tzinfo=AMS)   # 11:24 is minder dan 20 minuten weg
        r = plan([("1", None)], ["A"], {}, P, nu)
        self.assertEqual(lokaal(r[0][2]), "03 13:48")

    def test_dagmaximum_loopt_door_naar_morgen(self):
        nu = datetime(2026, 11, 3, 6, 0, tzinfo=AMS)
        r = plan([(str(i), None) for i in range(7)], ["A"], {}, P, nu)
        dagen = [t.astimezone(AMS).day for _, _, t in r]
        self.assertEqual(dagen, [3, 3, 3, 3, 3, 4, 4])

    def test_wat_er_al_staat_telt_mee(self):
        nu = datetime(2026, 11, 3, 6, 0, tzinfo=AMS)
        bezet = {"A": [datetime(2026, 11, 3, 9, 30, tzinfo=AMS), datetime(2026, 11, 3, 14, 0, tzinfo=AMS)]}
        r = plan([(str(i), None) for i in range(4)], ["A"], bezet, P, nu)
        # 9:00 en 13:48 liggen te dicht bij wat er al staat; per dag passen er nog 3
        self.assertEqual([lokaal(t) for _, _, t in r], ["03 11:24", "03 16:12", "03 18:36", "04 09:00"])
        alle = sorted(bezet["A"] + [t for _, _, t in r])
        self.assertTrue(all(b - a >= timedelta(minutes=45) for a, b in zip(alle, alle[1:])))

    def test_vast_account(self):
        nu = datetime(2026, 11, 3, 6, 0, tzinfo=AMS)
        r = plan([("1", "B"), ("2", None), ("3", None)], ["A", "B"], {}, P, nu)
        self.assertEqual([a for _, a, _ in r], ["B", "A", "B"])
        with self.assertRaises(PlanFout):
            plan([("1", "C")], ["A", "B"], {}, P, nu)

    def test_vanaf(self):
        nu = datetime(2026, 11, 3, 6, 0, tzinfo=AMS)
        r = plan([("1", None)], ["A"], {}, P, nu, vanaf=date(2026, 11, 10))
        self.assertEqual(lokaal(r[0][2]), "10 09:00")

    def test_geen_accounts(self):
        with self.assertRaises(PlanFout):
            plan([("1", None)], [], {}, P, datetime.now(timezone.utc))

    def test_past(self):
        t = datetime(2026, 11, 3, 12, 0, tzinfo=AMS)
        self.assertTrue(past(t, "A", {"A": [t - timedelta(minutes=45)]}, P))
        self.assertFalse(past(t, "A", {"A": [t - timedelta(minutes=44)]}, P))
        vol = {"A": [datetime(2026, 11, 3, h, 0, tzinfo=AMS) for h in (9, 15, 17, 19, 20)]}
        self.assertFalse(past(t, "A", vol, P))


if __name__ == "__main__":
    unittest.main()
