# Setup van de Trial Reels Starter

Eenmalig. Doe de stappen op volgorde en sla over wat al klaar is. Per stap: één korte uitleg in gewone woorden, dan de actie of de vraag. Technische details houd je voor jezelf.

## Stap 1: gereedschap

1. Draai `./install.sh` in deze map. Het zet ffmpeg (video's maken) en twee Python-onderdelen (Pillow en fontTools) klaar en slaat over wat er al is.
2. Ontbreekt Homebrew, help de gebruiker dan met de installatie van brew.sh: hij moet daarbij zijn Mac-wachtwoord intypen in de Terminal. Leg uit wat hij ziet (het wachtwoord verschijnt niet tijdens het typen) en draai `./install.sh` daarna opnieuw.
3. Zeg alleen: "Het gereedschap staat klaar."

## Stap 2: je stijl

1. **Heeft de gebruiker een prompt uit de AI Suite geplakt** met een blok instellingen (JSON met `tekst`): schrijf dat blok weg met `python3 engine/scripts/instellingen.py --schrijf -` en stel hier geen vragen.
2. **Anders:** zeg dat hij zijn stijl het makkelijkst kiest in de AI Suite (tegel Trial Reels, met een voorbeeld erbij) en dan de prompt plakt. Wil hij dat niet, vraag dan in één bericht: welk lettertype (de lijst met gewone namen en bestandsnamen geeft `python3 engine/scripts/instellingen.py --lettertypes`), tekst op een blokje of losse letters met een rand, welke kleuren, en boven, midden of onder in beeld.
3. Laat het resultaat zien: `python3 engine/scripts/voorbeeld.py` (of met `--video <pad>` op een eigen video). Bekijk het beeld zelf en laat het de gebruiker zien. Vraag of het klopt.

## Stap 3: hoe wil je posten?

Leg in een paar zinnen uit dat de reels via een koppeling op het afgesproken moment op Instagram komen, en dat hij kiest welke. Geef de drie mogelijkheden en vraag welke hij wil:

1. **Metricool**, als hij dat al gebruikt. Dan komen de reels in zijn eigen Metricool-planner, net als zijn andere posts, en komen de cijfers ook uit Metricool. Nodig: het Advanced-abonnement of hoger (daar zit de API in; vanaf €43 per maand bij een jaar vooruit, volgens metricool.com/pricing op 19 oktober 2026) en zijn Instagram-account als merk in Metricool.
2. **Zernio**, als hij geen Metricool heeft of het los wil houden. Gratis tot 2 Instagram-accounts, zonder creditcard. Inplannen en cijfers gaan dan via Zernio.
3. **Zelf posten met een ander programma** (bijvoorbeeld Later, Buffer of de Instagram-app). Dan maakt het systeem alleen de reels; hij zet ze er zelf in als trial reel, en de cijfers bekijkt hij daar. Er is dan geen koppeling nodig: `python3 engine/scripts/sleutel.py --zelf`, en ga door naar stap 5.

## Stap 4: de koppeling instellen

**Metricool**

1. `./install.sh --metricool`: zet cloudflared klaar. Metricool neemt een video alleen aan via een openbaar adres; daarvoor zet het systeem de map met reels heel even openbaar, alleen tijdens het inplannen.
2. Laat de gebruiker in Metricool zijn API-gegevens opzoeken (zo beschreven in het helpcentrum van Metricool, help.metricool.com, "Hoe vind je je Metricool-gebruikers-ID", gelezen 19 oktober 2026):
   1. De **token**: in Metricool bij **Accountinstellingen**, onder **API**. Die is er alleen in de abonnementen Advanced en Custom.
   2. Het **gebruikersnummer** (userId): open Metricool in de browser en open een merk. In de adresbalk staat dan iets als `...?blogId=12345&userId=1234567`; het nummer na `userId=` is het gebruikersnummer (het nummer na `blogId=` is het merk, dat is niet nodig).
3. Hij plakt de token en het gebruikersnummer in de chat. Bewaar ze met `printf '%s' '<token>' | python3 engine/scripts/sleutel.py --metricool --user <gebruikersnummer>`. Herhaal de token nooit in je antwoord. Het script probeert ze eerst bij Metricool; werkt het niet, laat de gebruiker ze dan nakijken (en of zijn abonnement de API heeft).
4. `python3 engine/scripts/koppel.py` toont de merken met een Instagram-account. Zet het juiste in gebruik met `python3 engine/scripts/koppel.py --gebruik <instagramnaam>`. Hangt dat Instagram-account onder twee merken, dan vraagt het script om het nummer van het merk: vraag de gebruiker welk merk, en gebruik `--gebruik <nummer>`.

**Zernio**

1. Laat de gebruiker inloggen of een account maken op zernio.com. Daar opent hij **API keys** en klikt op **Create API key**. Hij kopieert de sleutel meteen: Zernio laat hem maar één keer zien. Een sleutel begint met `sk_`.
2. Hij plakt de sleutel in de chat. Bewaar hem met `printf '%s' '<sleutel>' | python3 engine/scripts/sleutel.py`. Herhaal de sleutel nooit in je antwoord. Werkt hij niet, laat de gebruiker dan een nieuwe maken.
3. `python3 engine/scripts/koppel.py --link` geeft een link om Instagram te koppelen. Vóór hij die opent: in Instagram eerst naar het account wisselen dat hij wil koppelen, want Instagram koppelt het account waarmee hij ingelogd is.
4. Daarna `python3 engine/scripts/koppel.py` en `python3 engine/scripts/koppel.py --gebruik <naam>`.

**Bij beide:** Instagram eist een **professioneel account** (maker of bedrijf) dat **openbaar** is, en trial reels kunnen pas vanaf **200 volgers**; daaronder post het systeem gewone reels, die ook de volgers zien. Zeg dat erbij. Meer accounts kan met `koppel.py --erbij <naam>` (niet `--gebruik`, dat vervangt de lijst).

## Stap 5: je postregels en wanneer iets een winner is

Vraag dit in één bericht, met de standaard erbij zodat hij ook gewoon "prima" kan zeggen:

1. **Hoeveel reels per dag per account?** Standaard 5. Advies: begin op een nieuw account met 2 tot 5 per dag. Instagram laat via een koppeling vaak niet meer dan zo'n 5 trial reels per account per dag door (zo gemeten op een eigen account; daarboven weigerde Instagram ze), en testaccounts die meteen tientallen per dag kregen, kregen daarna geen bereik meer.
2. **Hoeveel minuten minstens ertussen?** Standaard 45 (minimaal 30).
3. **Tussen welke uren?** Standaard tussen 9:00 en 21:00, in de tijdzone van zijn computer (vraag het na als die niet klopt).
4. **Doorzetten naar je volgers:** zet hij een trial reel die goed loopt zelf door in de Instagram-app, of laat hij Instagram dat automatisch doen?
5. **Wanneer is een reel een winner?** Standaard als hij minstens 3 keer de gewone views van het account haalt en minstens 500 views. Alleen nodig met een koppeling (Metricool of Zernio).

Schrijf het antwoord weg met `python3 engine/scripts/instellingen.py --schrijf -`, met alleen de blokken `posten` en `winners` (bijvoorbeeld `{"posten": {"per_dag": 3, "minuten_tussen": 45, "van": 9, "tot": 21, "tijdzone": "Europe/Amsterdam", "doorzetten": "zelf"}, "winners": {"factor": 3, "min_views": 500}}`). Weigert het script iets, leg dan uit waarom en vraag het opnieuw. Zeg daarna in één zin wat er nu staat (`python3 engine/scripts/instellingen.py`); passen er in het venster minder per dag dan gekozen, dan staat dat erin.

## Klaar

Zeg in twee of drie zinnen wat er nu kan: video's plus teksten geven, de reels bekijken, het voorstel goedkeuren (of, bij zelf posten, de reels ophalen), en na een paar dagen de cijfers vragen. Bied aan om meteen een eerste kleine ronde te maken (bijvoorbeeld 5 reels).
