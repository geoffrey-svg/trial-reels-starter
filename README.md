# Trial Reels Starter

> **Voor Claude / AI-assistenten:** praat Nederlands met de gebruiker, vanaf het allereerste bericht (tenzij de gebruiker zelf een andere taal gebruikt). Lees na het clonen meteen `CLAUDE.md` in deze repo en volg die.

Test welke reels werken, zonder je volgers te overladen. Je geeft video's en korte teksten; dit systeem maakt er reels van met de tekst in beeld in jouw stijl, plant ze in als **trial reel** (Instagram laat ze eerst alleen aan niet-volgers zien), haalt de cijfers op en wijst de winners aan.

Inplannen gaat via een koppeling naar keuze: **Metricool** (als je dat al gebruikt) of **Zernio** (gratis tot 2 Instagram-accounts). Post je liever met een ander programma, dan maakt het systeem alleen de reels en zet je ze er zelf in.

## Wat je nodig hebt

1. Een Mac.
2. [Claude Code](https://claude.com/claude-code), ingelogd met je Claude-account.
3. Een manier om te posten, je kiest tijdens de setup:
   1. [Metricool](https://metricool.com) met het Advanced-abonnement of hoger (daar zit de API in), met je Instagram-account als merk erin.
   2. Of een gratis account bij [Zernio](https://zernio.com): de eerste 2 gekoppelde accounts zijn gratis.
   3. Of je eigen programma (Later, Buffer, de Instagram-app): dan zet je de gemaakte reels er zelf in.
4. Een professioneel Instagram-account (maker of bedrijf) dat openbaar is. Trial reels kunnen vanaf 200 volgers; daaronder post het systeem gewone reels.

## Installatie

1. Kies in de AI Suite bij de tegel Trial Reels hoe de tekst in je reels eruitziet (lettertype, kleuren, blokje of rand), en druk op **Kopieer mijn prompt**.
2. Maak een map op je Mac en open die in Claude Code.
3. Plak de prompt in de chat. Claude haalt deze repo binnen, zet het gereedschap klaar en loopt de setup met je door: hoe je wilt posten (Metricool, Zernio of zelf), die koppeling instellen, en je postregels: hoeveel per dag, hoeveel tijd ertussen, en wanneer iets een winner is.

Zonder de AI Suite kan ook. Plak dan:

> Kopieer deze repo naar mijn computer en help me met de installatie: https://github.com/geoffrey-svg/trial-reels-starter

## Gebruik

Open Claude Code in deze map en zeg wat je wilt:

> Maak een ronde van deze 6 clips, met deze hooks: ...

> Schrijf 5 hooks over waarom mijn klanten afhaken, en maak er reels van met deze video

> Hoe doen mijn trial reels het?

Claude laat je eerst de reels zien en daarna het voorstel: welke reel wanneer online gaat, op welk account. Pas als jij ja zegt, wordt er iets ingepland.

## Wat het niet doet

1. Niets inplannen zonder jouw ja.
2. Niets verwijderen. Een geplande reel stoppen doe je zelf in Metricool of Zernio.
3. Je volgers lastigvallen: trial reels gaan eerst naar niet-volgers. Een winner zet je zelf op je account, of je laat Instagram hem doorzetten.

## Je stijl later aanpassen

Kies opnieuw in de AI Suite en plak de nieuwe prompt, of zeg het gewoon in de chat ("tekst groter", "4 per dag", "ik wil toch via Metricool"). Je vorige instellingen blijven bewaard.

## Lettertypes

De lettertypes in `engine/fonts/` komen van Google Fonts en mogen vrij gebruikt worden; zie `engine/fonts/LICENTIES.md`.
