"""
Wanneer gaat elke reel online. Alleen rekenwerk, geen verbinding met Zernio.

Per account en per dag liggen de vaste tijden gelijk verspreid over het venster
(van tot tot, in de eigen tijdzone), hooguit per_dag stuks en minstens
minuten_tussen uit elkaar. Wat al gepland of gepost is, telt mee voor het
dagmaximum en voor de afstand. De reels gaan om de beurt naar de accounts.
"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

MARGE_MINUTEN = 20      # zo lang van tevoren moet een reel minstens klaarstaan
MAX_DAGEN = 366


class PlanFout(Exception):
    pass


DAGEN = ["ma", "di", "wo", "do", "vr", "za", "zo"]
MAANDEN = ["jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]


def nl(t, dag=True):
    """Een tijd zoals je hem in het Nederlands leest: di 20 okt 13:20."""
    return f"{DAGEN[t.weekday()] + ' ' if dag else ''}{t.day} {MAANDEN[t.month - 1]} {t:%H:%M}"


def dagtijden(dag, p):
    """De vaste tijden van één dag, als tijden met tijdzone."""
    tz = ZoneInfo(p["tijdzone"])
    venster = (p["tot"] - p["van"]) * 60
    aantal = max(1, min(p["per_dag"], venster // p["minuten_tussen"]))
    stap = venster / aantal
    begin = datetime.combine(dag, time(p["van"]))
    # Eerst de klok van die dag, dan pas de tijdzone: zo blijft 9:00 ook na de wissel naar wintertijd 9:00
    return [(begin + timedelta(minutes=round(i * stap))).replace(tzinfo=tz) for i in range(aantal)]


def plan(posts, accounts, bezet, p, nu, vanaf=None, marge=MARGE_MINUTEN):
    """
    posts:    lijst van (post_id, account_id of None); None betekent: om de beurt.
    accounts: de account-ids, in vaste volgorde.
    bezet:    {account_id: [tijden met tijdzone]} van wat er al staat.
    marge:    zo veel minuten vooruit op zijn vroegst (de koppeling bepaalt dat: Metricool wil een uur).
    Geeft [(post_id, account_id, tijd in UTC)] terug, op volgorde van de posts.
    """
    if not accounts:
        raise PlanFout("Er is nog geen account om op te posten.")
    tz = ZoneInfo(p["tijdzone"])
    vroegst = nu + timedelta(minutes=marge)
    eerste_dag = max(vroegst.astimezone(tz).date(), vanaf or date.min)
    tussen = timedelta(minutes=p["minuten_tussen"])
    # Rekenen in UTC: Python trekt twee tijden met dezelfde tijdzone af op de klok, en dan klopt een uur rond de wissel niet
    gepland = {a: sorted(t.astimezone(timezone.utc) for t in bezet.get(a, [])) for a in accounts}

    def vrij(account, tijd):
        dag = tijd.astimezone(tz).date()
        op_dag = sum(1 for t in gepland[account] if t.astimezone(tz).date() == dag)
        return op_dag < p["per_dag"] and all(abs(t - tijd) >= tussen for t in gepland[account])

    def volgende(account):
        for d in range(MAX_DAGEN):
            for tijd in dagtijden(eerste_dag + timedelta(days=d), p):
                tijd = tijd.astimezone(timezone.utc)
                if tijd >= vroegst and vrij(account, tijd):
                    return tijd
        raise PlanFout("Binnen een jaar is er geen plek meer vrij. Plan minder reels of zet er meer per dag.")

    uit, beurt = [], 0
    for post_id, vast in posts:
        if vast is not None and vast not in accounts:
            raise PlanFout(f"Post {post_id} moet naar een account dat niet in gebruik is.")
        account = vast if vast is not None else accounts[beurt % len(accounts)]
        if vast is None:
            beurt += 1
        tijd = volgende(account)
        gepland[account].append(tijd)
        uit.append((post_id, account, tijd))
    return uit


def past(tijd, account, bezet, p):
    """Of een tijd uit een eerder voorstel nog past naast wat er nu bij dat account staat."""
    tz = ZoneInfo(p["tijdzone"])
    anderen = [t.astimezone(timezone.utc) for t in bezet.get(account, [])]
    tijd = tijd.astimezone(timezone.utc)
    dag = tijd.astimezone(tz).date()
    tussen = timedelta(minutes=p["minuten_tussen"])
    return (sum(1 for t in anderen if t.astimezone(tz).date() == dag) < p["per_dag"]
            and all(abs(t - tijd) >= tussen for t in anderen))
