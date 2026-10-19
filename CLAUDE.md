# Trial Reels Starter

Dit is de starter-repo van een eigen trial reels-systeem. Lees dit eerst, bij elke sessie.

## Taal en toon

Praat NEDERLANDS, vanaf het allereerste bericht, tenzij de gebruiker zelf in een andere taal schrijft. De gebruiker is meestal niet technisch: geen jargon, geen scriptnamen of foutcodes in je antwoord, korte zinnen. Wat er technisch gebeurt houd je voor jezelf; de gebruiker krijgt hooguit één zin ("Ik zet de gereedschappen klaar... klaar.") en daarna de volgende vraag of het resultaat.

## Wat dit systeem doet

1. Van video's plus een korte tekst maakt het staande reels (1080 bij 1920) met de tekst in beeld, in de eigen stijl van de gebruiker: lettertype, kleuren, tekstblok of rand, plek in beeld.
2. Het plant ze in op Instagram als **trial reel**: Instagram laat zo'n reel eerst alleen aan niet-volgers zien. Zo test de gebruiker hooks en onderwerpen zonder zijn volgers te overladen.
3. Inplannen gaat via een **koppeling** die de gebruiker zelf kiest: **Metricool** (als hij dat al gebruikt, met het Advanced-abonnement of hoger, want daar zit de API in) of **Zernio** (gratis tot 2 Instagram-accounts). Post hij liever met een ander programma (Later, Buffer, de Instagram-app), dan maakt het systeem alleen de reels en zet hij ze er zelf in.
4. Met een koppeling haalt het de cijfers op en wijst het de winners aan: reels die veel beter doen dan gewoon op dat account.

## Welke modus?

1. **Setup.** Lees `setup/SKILL.md` en begin meteen met de eerste stap die nog niet gedaan is, zonder te vragen "zal ik de setup starten?". De setup is niet af als: er nog geen keuze is hoe hij post (`mijn-trial-reels/koppeling.json` én `mijn-trial-reels/accounts.json` ontbreken), of de koppeling is Metricool of Zernio en `accounts.json` ontbreekt, of `python3 engine/scripts/instellingen.py` meldt "Nog niet (helemaal) gekozen: de postregels". Staat `accounts.json` er wel maar `koppeling.json` niet, dan is het een installatie van voor de keuze: die post via Zernio met de sleutel die er al staat, en de setup is af (vraag geen nieuwe sleutel). Geeft de gebruiker meteen een opdracht, zeg dan in één zin dat de eenmalige setup eerst moet en begin.
2. **Werken.** Staat alles er, volg dan de hoofdstukken hieronder.

Plakt de gebruiker een prompt uit de AI Suite met een blok instellingen erin: zie "Instellingen".

## Harde regels

1. **Nooit iets inplannen zonder een duidelijke ja van de gebruiker, in de chat, op het voorstel van precies die ronde.** Altijd eerst het voorstel (`plan_ronde.py <ronde>`) laten zien, in gewone woorden. Pas na "ja", "doe maar" of iets wat daar ondubbelzinnig op lijkt draai je `--echt`. Een ja geldt voor die ene ronde, niet voor de volgende.
2. **Nooit iets verwijderen**, niet op deze computer en niet bij Metricool, Zernio of Instagram. Wil de gebruiker een geplande reel stoppen, dan doet hij dat zelf in Metricool of Zernio. Bestanden die weg moeten, gaan naar een map `oud/`.
3. **Sleutels en tokens** (van Zernio of Metricool) gaan alleen via `engine/scripts/sleutel.py` naar `~/.config/trial-reels-starter/`. Nooit in dit project, nooit in een bestand dat je laat zien, nooit herhalen in de chat, nooit in git.
4. **Gewone reels zien ook volgers.** Een account met minder dan 200 volgers kan nog geen trial reels posten (regel van Instagram); het systeem post daar gewone reels. Zeg dat altijd vóór je inplant, met welk account het is.
5. **Postregels niet zelf ophogen.** Hoeveel per dag en hoeveel minuten ertussen heeft de gebruiker zelf gekozen; die staan in de instellingen. Op een vers account adviseer je rustig te beginnen (2 tot 5 per dag de eerste week): testaccounts die meteen tientallen reels per dag kregen, kregen daarna van Instagram geen bereik meer.
6. `engine/`, `templates/` en `setup/` zijn het product en pas je tijdens het werk niet aan. Alles van de gebruiker staat in `mijn-trial-reels/`.
7. **Lange commando's helemaal laten uitlopen.** Reels maken duurt ongeveer zo lang als de video's samen, en `--echt` zet elke reel bij de koppeling (bij Metricool komt daar eerst een tunnel bij, ruim anderhalve minuut). Draai `maak_reels.py` en `plan_ronde.py --echt` daarom met een ruime tijdgrens (10 minuten) of op de achtergrond, en wacht tot ze klaar zijn. Start nooit hetzelfde commando voor dezelfde ronde opnieuw terwijl het nog loopt; het systeem weigert dat ook ("Er loopt al iets voor deze ronde"). Na een onderbreking draai je het gewoon opnieuw: wat klaar was, blijft klaar, en niets komt dubbel.

## Een ronde maken en inplannen

1. **Materiaal.** De gebruiker levert video's (eigen clips of beeldmateriaal, staand of liggend, 3 tot 90 seconden; een stuk uit een langere video kan met `van` en `tot`) en per reel een tekst in beeld (de hook) en een caption. Wil hij hulp met hooks: schrijf varianten op één idee en geef elke variant een korte `angle` (bijvoorbeeld "pijn", "droom", "fout"), dan laten de cijfers later zien welke soort wint. Gebruik nooit dezelfde video met dezelfde tekst twee keer.
2. **Ronde vastleggen.** Maak `mijn-trial-reels/rondes/<JJJJ-MM-DD>-<korte-naam>/ronde.json`, zoals `templates/ronde-voorbeeld.json`. Paden naar video's mogen absoluut zijn. Een vast account per reel kan met `"account": "gebruikersnaam"`; anders gaan ze om de beurt.
3. **Nakijken en maken.** `python3 engine/scripts/maak_reels.py <ronde> --controleer`, en als alles klopt zonder `--controleer`. Klopt een tekst niet (te lang, een teken dat het lettertype en het emojifont niet hebben, een vlag of een emoji met huidskleur), stel dan een kortere of andere tekst voor. Een te lang woord krijgt eerst vanzelf een iets kleinere letter.
4. **Laten zien.** Bekijk zelf het contactvel (het pad staat in de uitvoer) en laat het de gebruiker zien. Moet er een anders, pas `ronde.json` aan en draai `maak_reels.py <ronde>` opnieuw: een reel waarvan de tekst, het stuk video of de stijl veranderde, wordt vanzelf opnieuw gemaakt (de oude gaat naar `klaar/oud/`). Zonder iets te veranderen opnieuw maken kan met `--opnieuw <id>`. De oorspronkelijke video's mogen daarna verhuizen; inplannen gebruikt de gemaakte reels.
5. **Post de gebruiker zelf** (koppeling "zelf"): dan stopt het hier. Zeg waar de reels staan (`klaar/` in de ronde) en geef per reel de caption, zodat hij ze in zijn eigen programma als trial reel kan inplannen. Stel desgewenst een planning voor volgens zijn postregels, in de chat.
6. **Voorstel.** `python3 engine/scripts/plan_ronde.py <ronde>`. Vertel in gewone woorden: hoeveel reels, van wanneer tot wanneer, via welke koppeling, op welk account, trial of gewoon, en of Instagram een goede trial reel vanzelf doorzet naar de volgers. Staat er "Al bij ... uit deze ronde", noem dat ook; staat er "Opnieuw in dit voorstel", zeg dat die reels eerder gestopt of mislukt waren en nu opnieuw meegaan. Vraag dan: "Zal ik deze reels zo inplannen?" Zegt het script dat de koppeling het aantal volgers niet weet, vraag dan of het account al 200 volgers heeft en maak het voorstel opnieuw met `--soort trial` of `--soort gewoon`. Via Metricool plant het voorstel op zijn vroegst een uur vooruit.
7. **Inplannen, alleen na ja.** `python3 engine/scripts/plan_ronde.py <ronde> --echt` (zie harde regel 7 over de tijd). Zegt het dat het voorstel verouderd is (een reel, caption, postregel of de koppeling veranderde, of er kwam iets bij), maak dan een nieuw voorstel en vraag opnieuw. Meldt het MISLUKT bij een reel, vertel de reden in gewone taal. Bij Metricool staat die post er dan wel, maar gaat hij niet goed (de video kwam niet aan, of Metricool bewaarde een andere tijd, soort of caption): de gebruiker stopt die post in Metricool, en daarna neemt een nieuw voorstel de reel vanzelf opnieuw mee. Zegt het dat de video's via de tunnel niet bereikbaar zijn, dan is er niets ingepland: probeer het over een paar minuten één keer opnieuw. Lukt het dan weer niet, stop dan en zeg dat Metricool de video's vanaf deze computer niet kan ophalen (bijvoorbeeld door een bedrijfsnetwerk of firewall); stel voor het later of op een ander netwerk te proberen, of via Zernio te posten. Zegt het voorstel "Niet in dit voorstel" omdat een reel half via een vorige koppeling ging, volg dan wat er staat: die koppeling even terugzetten met `sleutel.py --bewaard`, of de gebruiker daar zelf laten kijken en alleen als hij hem daar niet ziet `plan_ronde.py <ronde> --vrijgeven <id>`.
8. **Stand.** `plan_ronde.py <ronde> --stand` laat zien wat gepland, online, mislukt of in de koppeling gestopt is, met de reden van Instagram. Vertel een mislukte reden in gewone taal en stel een oplossing voor. Een reel die mislukte, of die de gebruiker in de koppeling stopte voordat zijn tijd kwam, neemt een nieuw voorstel vanzelf opnieuw mee; wil hij die reel niet meer, haal hem dan uit `ronde.json`. Zeg erbij dat hij een mislukte reel niet zelf opnieuw inplant in Metricool of Zernio: dat doet het voorstel, anders staat hij er twee keer. Is een reel uit de koppeling verdwenen nadat zijn tijd voorbij was, dan gaat hij niet vanzelf opnieuw mee (hij kan al online staan): volg wat de stand zegt. Zegt het dat een reel opnieuw gemaakt is nadat hij was ingepland, dan staat bij de koppeling nog de oude versie: vraag de gebruiker die daar te stoppen als hij de nieuwe wil, en maak daarna een nieuw voorstel.

## Cijfers en winners

1. Cijfers van Instagram zijn pas na ongeveer 48 uur betrouwbaar; eerder telt een reel niet mee. Metricool loopt daarbij nog ruim een dag achter.
2. `python3 engine/scripts/cijfers.py` (standaard de laatste 30 dagen, anders `--dagen 90`). Lees het verslag dat het schrijft en vertel in een paar regels: de winners met hun tekst, welke angle het best doet, en elke waarschuwing (bijvoorbeeld een account zonder bereik, een account waarvan de koppeling geen cijfers gaf, of reels die via een andere koppeling gingen). Met de koppeling "zelf" zijn er geen cijfers: die bekijkt de gebruiker in zijn eigen programma.
3. Een winner zet de gebruiker op zijn hoofdaccount als nieuwe video, niet als hetzelfde bestand. Of hij laat Instagram doorzetten: met "automatisch doorzetten" in de instellingen deelt Instagram een trial reel die goed loopt vanzelf met de volgers.

## Instellingen

1. De instellingen staan in `mijn-trial-reels/config.json`; `python3 engine/scripts/instellingen.py` zegt ze in gewone woorden.
2. **Uit de AI Suite:** plakt de gebruiker een prompt met een blok JSON (met `tekst`: hoe de tekst in beeld eruitziet), schrijf dat blok dan precies zo weg met `python3 engine/scripts/instellingen.py --schrijf -` (het blok via stdin). Stel daarna geen vragen over de stijl; laat een voorbeeld zien met `python3 engine/scripts/voorbeeld.py` en bekijk het zelf ook. De postregels en de winners staan niet in dat blok: die vraag je in de setup (stap 5).
3. **In de chat:** vraagt de gebruiker iets anders ("tekst groter", "4 per dag"), schrijf dan alleen dat veld weg met `--schrijf -` en laat bij een stijlwijziging het voorbeeld zien. Kan iets niet (bijvoorbeeld meer dan 20 per dag), zeg dat en waarom. De lettertypes met hun bestandsnaam: `python3 engine/scripts/instellingen.py --lettertypes`. Reels die al gemaakt zijn met de oude stijl, worden bij de volgende `maak_reels.py` vanzelf opnieuw gemaakt.
4. De vorige instellingen blijven bewaard in `mijn-trial-reels/oud/`.

## Koppeling en accounts

1. De koppeling staat in `mijn-trial-reels/koppeling.json` en wordt gezet met `engine/scripts/sleutel.py` (zie setup stap 3 en 4). Wisselen kan altijd: staat de sleutel of token van de andere koppeling hier al, dan met `sleutel.py --bewaard zernio` of `--bewaard metricool` (geen nieuwe nodig), anders zoals in de setup. Kies daarna de accounts opnieuw (`koppel.py` en `koppel.py --gebruik`), want elke koppeling heeft eigen nummers, en maak een nieuw voorstel. Reels die al via de oude koppeling klaarstaan, blijven daar en gaan gewoon online; ze tellen mee als bezet, en hun stand en cijfers zie je via die oude koppeling. Kwam bij de oude koppeling een antwoord niet aan, dan weigert het voorstel die reel via de nieuwe: zet dan eerst even de oude terug, zoals de melding zegt.
2. `python3 engine/scripts/koppel.py` toont de Instagram-accounts in de koppeling, met volgers en of ze trial reels kunnen. Bij Metricool is elk merk met een Instagram-account erin een account.
3. Zernio: `koppel.py --link` geeft een link om een account te koppelen. Instagram koppelt het account waarmee de gebruiker op dat moment ingelogd is: laat hem in Instagram eerst naar het goede account wisselen. Metricool: de gebruiker koppelt Instagram in Metricool zelf (een merk met het Instagram-account erin).
4. `koppel.py --gebruik <naam> [<naam> ...]` legt vast op welke accounts het systeem post (alleen die). Een account erbij, terwijl de rest blijft: `koppel.py --erbij <naam>`. Hangt hetzelfde Instagram-account bij Metricool onder twee merken, dan vraagt het om het nummer van het merk: vraag de gebruiker op welk merk hij wil posten en gebruik dat nummer. Wat er op de andere merken met dat account gepland staat, telt gewoon mee.
5. Kosten: bij Zernio zijn de eerste 2 gekoppelde accounts gratis, daarna per account per maand (zernio.com/pricing); noem dat voordat de gebruiker een derde account koppelt. Bij Metricool betaalt de gebruiker zijn eigen abonnement; de API zit in Advanced en hoger.

## Structuur

1. `setup/SKILL.md`: de eenmalige setup.
2. `engine/scripts/`: de scripts. `engine/fonts/`: de lettertypes.
3. `templates/`: de standaardinstellingen en een voorbeeldronde.
4. `mijn-trial-reels/`: alles van de gebruiker (instellingen, koppeling, accounts, rondes, cijfers). Staat niet in git.
5. `tests/`: `python3 -m unittest discover -s tests`, alleen nodig als iets vreemd doet.

## Bijwerken

`git pull` in deze map haalt de nieuwste versie. `mijn-trial-reels/` blijft daarbij staan.
