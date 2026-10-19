# Setup van de Trial Reels Starter

Eenmalig, een kwartiertje. Doe de stappen op volgorde en sla over wat al klaar is. Per stap: één korte uitleg in gewone woorden, dan de actie. Technische details houd je voor jezelf.

## Stap 1: gereedschap

1. Draai `./install.sh` in deze map. Het zet ffmpeg (video's maken) en twee Python-onderdelen (Pillow en fontTools) klaar en slaat over wat er al is.
2. Ontbreekt Homebrew, help de gebruiker dan met de installatie van brew.sh: hij moet daarbij zijn Mac-wachtwoord intypen in de Terminal. Leg uit wat hij ziet (het wachtwoord verschijnt niet tijdens het typen) en draai `./install.sh` daarna opnieuw.
3. Zeg alleen: "Het gereedschap staat klaar."

## Stap 2: je stijl en je postregels

1. **Heeft de gebruiker een prompt uit de AI Suite geplakt** met een blok instellingen (JSON met `tekst`, `posten` en `winners`): schrijf dat blok weg met `python3 engine/scripts/instellingen.py --schrijf -` en stel hier geen vragen.
2. **Anders:** zeg dat hij zijn stijl het makkelijkst kiest in de AI Suite (tegel Trial Reels, met een voorbeeld erbij) en dan de prompt plakt. Wil hij dat niet, vraag dan in één bericht: welk lettertype (de lijst met gewone namen en bestandsnamen geeft `python3 engine/scripts/instellingen.py --lettertypes`), tekst op een blokje of losse letters met een rand, welke kleuren, en boven, midden of onder in beeld. Postregels blijven dan op de standaard (5 per dag, 45 minuten ertussen, tussen 9 en 21 uur); noem die en vraag of het goed is.
3. Laat het resultaat zien: `python3 engine/scripts/voorbeeld.py` (of met `--video <pad>` op een eigen video). Bekijk het beeld zelf en laat het de gebruiker zien. Vraag of het klopt.

## Stap 3: Zernio

Zernio is de dienst die de reels op het afgesproken moment op Instagram zet en de cijfers ophaalt. De eerste 2 gekoppelde accounts zijn gratis, zonder creditcard.

1. Laat de gebruiker inloggen of een account maken op zernio.com.
2. Daar opent hij **API keys** en klikt op **Create API key**. Hij kopieert de sleutel meteen: Zernio laat hem maar één keer zien. Een sleutel begint met `sk_`.
3. Hij plakt de sleutel in de chat. Bewaar hem met `printf '%s' '<sleutel>' | python3 engine/scripts/sleutel.py`. Herhaal de sleutel nooit in je antwoord. Het script probeert hem eerst bij Zernio; zegt het dat hij niet werkt, laat de gebruiker dan een nieuwe maken.

## Stap 4: Instagram koppelen

1. Eisen van Instagram: een **professioneel account** (maker of bedrijf) dat **openbaar** is. Trial reels kunnen pas vanaf **200 volgers**; daaronder post het systeem gewone reels, die ook de volgers zien. Zeg dat erbij.
2. `python3 engine/scripts/koppel.py --link` geeft een link. Vóór hij die opent: in Instagram eerst naar het account wisselen dat hij wil koppelen, want Instagram koppelt het account waarmee hij ingelogd is.
3. Daarna `python3 engine/scripts/koppel.py`: staat het account erbij? Leg dan vast welk account het systeem gebruikt met `python3 engine/scripts/koppel.py --gebruik <naam>`.
4. Meer accounts kan: koppel het met `koppel.py --link` en zet het erbij met `koppel.py --erbij <naam>` (niet `--gebruik`, dat vervangt de lijst). Vanaf het derde account kost het geld bij Zernio.

## Klaar

Zeg in twee of drie zinnen wat er nu kan: video's plus teksten geven, de reels bekijken, het voorstel goedkeuren, en na een paar dagen de cijfers vragen. Bied aan om meteen een eerste kleine ronde te maken (bijvoorbeeld 5 reels).
