# Trial Reels Starter

Dit is de starter-repo van een eigen trial reels-systeem. Lees dit eerst, bij elke sessie.

## Taal en toon

Praat NEDERLANDS, vanaf het allereerste bericht, tenzij de gebruiker zelf in een andere taal schrijft. De gebruiker is meestal niet technisch: geen jargon, geen scriptnamen of foutcodes in je antwoord, korte zinnen. Wat er technisch gebeurt houd je voor jezelf; de gebruiker krijgt hooguit één zin ("Ik zet de gereedschappen klaar... klaar.") en daarna de volgende vraag of het resultaat.

## Wat dit systeem doet

1. Van video's plus een korte tekst maakt het staande reels (1080 bij 1920) met de tekst in beeld, in de eigen stijl van de gebruiker: lettertype, kleuren, tekstblok of rand, plek in beeld.
2. Het plant ze in op Instagram als **trial reel**: Instagram laat zo'n reel eerst alleen aan niet-volgers zien. Zo test de gebruiker hooks en onderwerpen zonder zijn volgers te overladen. Posten loopt via Zernio, op het eigen Zernio-account van de gebruiker.
3. Het haalt de cijfers op en wijst de winners aan: reels die veel beter doen dan gewoon op dat account.

## Welke modus?

1. **Setup.** Ontbreekt `mijn-trial-reels/config.json`, `mijn-trial-reels/accounts.json` of de Zernio-sleutel (`python3 engine/scripts/koppel.py` zegt dan dat er geen sleutel is), lees dan `setup/SKILL.md` en begin meteen met de eerste stap die nog niet gedaan is. Vraag niet "zal ik de setup starten?". Geeft de gebruiker meteen een opdracht, zeg dan in één zin dat de eenmalige setup eerst moet en begin.
2. **Werken.** Staat alles er, volg dan de hoofdstukken hieronder.

Plakt de gebruiker een prompt uit de AI Suite met een blok instellingen erin: zie "Instellingen".

## Harde regels

1. **Nooit iets inplannen zonder een duidelijke ja van de gebruiker, in de chat, op het voorstel van precies die ronde.** Altijd eerst het voorstel (`plan_ronde.py <ronde>`) laten zien, in gewone woorden. Pas na "ja", "doe maar" of iets wat daar ondubbelzinnig op lijkt draai je `--echt`. Een ja geldt voor die ene ronde, niet voor de volgende.
2. **Nooit iets verwijderen**, niet op deze computer en niet bij Zernio of Instagram. Wil de gebruiker een geplande reel stoppen, dan doet hij dat zelf in het dashboard van Zernio. Bestanden die weg moeten, gaan naar een map `oud/`.
3. **De Zernio-sleutel** gaat alleen via `engine/scripts/sleutel.py` naar `~/.config/trial-reels-starter/`. Nooit in dit project, nooit in een bestand dat je laat zien, nooit herhalen in de chat, nooit in git.
4. **Gewone reels zien ook volgers.** Een account met minder dan 200 volgers kan nog geen trial reels posten (regel van Instagram); het systeem post daar gewone reels. Zeg dat altijd vóór je inplant, met welk account het is.
5. **Postregels niet zelf ophogen.** Hoeveel per dag en hoeveel minuten ertussen staat in de instellingen. Op een vers account adviseer je rustig te beginnen (2 tot 5 per dag de eerste week): testaccounts die meteen tientallen reels per dag kregen, kregen daarna van Instagram geen bereik meer.
6. `engine/`, `templates/` en `setup/` zijn het product en pas je tijdens het werk niet aan. Alles van de gebruiker staat in `mijn-trial-reels/`.
7. **Lange commando's helemaal laten uitlopen.** Reels maken duurt ongeveer zo lang als de video's samen, en `--echt` uploadt elke reel. Draai `maak_reels.py` en `plan_ronde.py --echt` daarom met een ruime tijdgrens (10 minuten) of op de achtergrond, en wacht tot ze klaar zijn. Start nooit hetzelfde commando voor dezelfde ronde opnieuw terwijl het nog loopt; het systeem weigert dat ook ("Er loopt al iets voor deze ronde"). Na een onderbreking draai je het gewoon opnieuw: wat klaar was, blijft klaar, en niets komt dubbel.

## Een ronde maken en inplannen

1. **Materiaal.** De gebruiker levert video's (eigen clips of beeldmateriaal, staand of liggend, 3 tot 90 seconden; een stuk uit een langere video kan met `van` en `tot`) en per reel een tekst in beeld (de hook) en een caption. Wil hij hulp met hooks: schrijf varianten op één idee en geef elke variant een korte `angle` (bijvoorbeeld "pijn", "droom", "fout"), dan laten de cijfers later zien welke soort wint. Gebruik nooit dezelfde video met dezelfde tekst twee keer.
2. **Ronde vastleggen.** Maak `mijn-trial-reels/rondes/<JJJJ-MM-DD>-<korte-naam>/ronde.json`, zoals `templates/ronde-voorbeeld.json`. Paden naar video's mogen absoluut zijn. Een vast account per reel kan met `"account": "gebruikersnaam"`; anders gaan ze om de beurt.
3. **Nakijken en maken.** `python3 engine/scripts/maak_reels.py <ronde> --controleer`, en als alles klopt zonder `--controleer`. Klopt een tekst niet (te lang, een teken dat het lettertype en het emojifont niet hebben, een vlag of een emoji met huidskleur), stel dan een kortere of andere tekst voor. Een te lang woord krijgt eerst vanzelf een iets kleinere letter.
4. **Laten zien.** Bekijk zelf het contactvel (het pad staat in de uitvoer) en laat het de gebruiker zien. Moet er een anders, pas `ronde.json` aan en draai `maak_reels.py <ronde>` opnieuw: een reel waarvan de tekst, het stuk video of de stijl veranderde, wordt vanzelf opnieuw gemaakt (de oude gaat naar `klaar/oud/`). Zonder iets te veranderen opnieuw maken kan met `--opnieuw <id>`. De oorspronkelijke video's mogen daarna verhuizen; inplannen gebruikt de gemaakte reels.
5. **Voorstel.** `python3 engine/scripts/plan_ronde.py <ronde>`. Vertel in gewone woorden: hoeveel reels, van wanneer tot wanneer, op welk account, trial of gewoon, en of Instagram een goede trial reel vanzelf doorzet naar de volgers. Staat er "Al bij Zernio uit deze ronde", noem dat ook. Vraag dan: "Zal ik deze reels zo inplannen?" Zegt het script dat Zernio het aantal volgers niet weet, vraag dan of het account al 200 volgers heeft en maak het voorstel opnieuw met `--soort trial` of `--soort gewoon`.
6. **Inplannen, alleen na ja.** `python3 engine/scripts/plan_ronde.py <ronde> --echt` (zie harde regel 7 over de tijd). Zegt het dat het voorstel verouderd is (een reel, caption of postregel veranderde, of er kwam iets bij in Zernio), maak dan een nieuw voorstel en vraag opnieuw. Meldt het MISLUKT bij een reel, vertel de reden in gewone taal.
7. **Stand.** `plan_ronde.py <ronde> --stand` laat zien wat gepland, online, mislukt of in Zernio gestopt is, met de reden van Instagram. Vertel een mislukte reden in gewone taal en stel een oplossing voor. Zegt het dat een reel opnieuw gemaakt is nadat hij was ingepland, dan staat bij Zernio nog de oude versie: vraag de gebruiker die in Zernio te stoppen als hij de nieuwe wil, en plan de ronde daarna opnieuw in.

## Cijfers en winners

1. Cijfers van Instagram zijn pas na ongeveer 48 uur betrouwbaar; eerder telt een reel niet mee.
2. `python3 engine/scripts/cijfers.py` (standaard de laatste 30 dagen, anders `--dagen 90`). Lees het verslag dat het schrijft en vertel in een paar regels: de winners met hun tekst, welke angle het best doet, en elke waarschuwing (bijvoorbeeld een account zonder bereik).
3. Een winner zet de gebruiker op zijn hoofdaccount als nieuwe video, niet als hetzelfde bestand. Of hij laat Instagram doorzetten: met "automatisch doorzetten" in de instellingen deelt Instagram een trial reel die goed loopt vanzelf met de volgers.

## Instellingen

1. De instellingen staan in `mijn-trial-reels/config.json`; `python3 engine/scripts/instellingen.py` zegt ze in gewone woorden.
2. **Uit de AI Suite:** plakt de gebruiker een prompt met een blok JSON (met `tekst`, `posten` en `winners`), schrijf dat blok dan precies zo weg met `python3 engine/scripts/instellingen.py --schrijf -` (het blok via stdin). Stel daarna geen vragen over stijl of postregels; laat een voorbeeld zien met `python3 engine/scripts/voorbeeld.py` en bekijk het zelf ook.
3. **In de chat:** vraagt de gebruiker iets anders ("tekst groter", "4 per dag"), schrijf dan alleen dat veld weg met `--schrijf -` en laat het voorbeeld zien. Kan iets niet (bijvoorbeeld meer dan 20 per dag), zeg dat en waarom. De lettertypes met hun bestandsnaam: `python3 engine/scripts/instellingen.py --lettertypes`. Reels die al gemaakt zijn met de oude stijl, worden bij de volgende `maak_reels.py` vanzelf opnieuw gemaakt.
4. De vorige instellingen blijven bewaard in `mijn-trial-reels/oud/`.

## Accounts

1. `python3 engine/scripts/koppel.py` toont de Instagram-accounts in Zernio, met volgers en of ze trial reels kunnen.
2. `python3 engine/scripts/koppel.py --link` geeft een link om een account te koppelen. Instagram koppelt het account waarmee de gebruiker op dat moment ingelogd is: laat hem in Instagram eerst naar het goede account wisselen.
3. `python3 engine/scripts/koppel.py --gebruik <naam> [<naam> ...]` legt vast op welke accounts het systeem post (alleen die). Een account erbij, terwijl de rest blijft: `koppel.py --erbij <naam>`.
4. Kosten bij Zernio: de eerste 2 gekoppelde accounts zijn gratis, daarna per account per maand (zie zernio.com/pricing). Noem dat voordat de gebruiker een derde account koppelt.

## Structuur

1. `setup/SKILL.md`: de eenmalige setup.
2. `engine/scripts/`: de scripts. `engine/fonts/`: de lettertypes.
3. `templates/`: de standaardinstellingen en een voorbeeldronde.
4. `mijn-trial-reels/`: alles van de gebruiker (instellingen, accounts, rondes, cijfers). Staat niet in git.
5. `tests/`: `python3 -m unittest discover -s tests`, alleen nodig als iets vreemd doet.

## Bijwerken

`git pull` in deze map haalt de nieuwste versie. `mijn-trial-reels/` blijft daarbij staan.
