# Resultaten publiceren op de WordPress-clubwebsite

Datum: 28 oktober 2026

## Doel en huidige situatie

De competitiebeheerder beheert de clubwebsite via WordPress:
https://thestallionbullets.be/

Op de competitiepagina staan aparte links naar speeldaguitslagen, het klassement, hoogste finishes en 180-worpen:
https://thestallionbullets.be/maandelijkse-competitie/

De Django-webapp berekent resultaten en klassementen en draait lokaal zonder gebruikersaccounts. De app heeft een kopieerfunctie voor WordPress, maar geen rechtstreekse WordPress-API-koppeling.

## Beschikbaar: kopiëren en plakken

Op het seizoenoverzicht en de seizoenstand staat **Kopiëren voor WordPress**. Eén klik kopieert de volledige seizoensbundel als HTML-tabellen naar het klembord. Op afzonderlijke overzichtstabellen, ook op een competitieavond, staat daarnaast **Tabel kopiëren** om alleen die tabel te kopiëren.

Op de printpagina staat één knop **Briefjes kopiëren voor WordPress** bovenaan. Die kopieert alle voltooide wedstrijdbriefjes tegelijk, inclusief datum, wedstrijdgegevens, uitslag, worpstatistieken en schrijver. Onvoltooide briefjes worden overgeslagen en de knop wordt niet mee afgedrukt.

- Alle wedstrijden en uitslagen van het seizoen.
- Per speler de 171/180-worpen, finishes en pijlen per wedstrijd.
- Het puntenklassement en de klassementen voor 180, 171, hoogste finish (tot 170) en minste pijlen.
- De tussenstand van iedere competitieavond.

Werkwijze voor de beheerder:

1. Werk de resultaten in de app bij.
2. Klik op **Kopiëren voor WordPress**.
3. Plak de tabellen in de gewenste WordPress-pagina en werk die bij.

Dit vraagt geen automatische koppeling of extra hosting. De tabellen worden als HTML gekopieerd, zodat de WordPress-editor ze als tabellen kan plakken. Controleer na het plakken de opmaak in de gebruikte editor.

**Voordeel:** geen toegang tot WordPress nodig vanuit de app; wijzigingen zijn met één export beschikbaar.

**Nadeel:** na iedere speeldag of correctie moet de beheerder de bijgewerkte tabellen handmatig in WordPress plakken.

## Optie 2: rechtstreeks publiceren vanuit de app

Voeg een knop **Publiceren naar website** toe die via de WordPress REST API de juiste pagina's bijwerkt.

Eenmalige voorbereiding:

- Bepaal welke WordPress-pagina bij elke uitslag of elk klassement hoort.
- Spreek af of de app een volledige pagina of alleen een afgebakend resultatengedeelte beheert, zodat andere inhoud behouden blijft.
- Stel een apart WordPress-account in met alleen de benodigde rechten.
- Gebruik een Application Password via HTTPS en bewaar dit buiten de broncode.
- Controleer of de WordPress-installatie en eventuele beveiligingsplugins deze toegang toestaan.

Na een speeldag publiceert de beheerder vanuit de app. Bij correcties worden dezelfde doelpagina's bijgewerkt. De website blijft beschikbaar wanneer de lokale app gesloten is; de app heeft alleen tijdens het publiceren een internetverbinding nodig.

**Voordeel:** geen handmatig kopieerwerk en de bestaande website blijft het publieke aanspreekpunt.

**Nadeel:** meer implementatie en eenmalige configuratie nodig, inclusief beveiligde opslag van de toegangsgegevens en duidelijke foutmeldingen bij publicatieproblemen.

## Optie 3: de volledige app online plaatsen

De app kan op een subdomein worden gehost, bijvoorbeeld `competitie.thestallionbullets.be`, met een link vanuit WordPress.

Daarvoor zijn geschikte Django-hosting, HTTPS, gebruikersaccounts, toegangsbeveiliging, productie-instellingen en een back-upstrategie nodig. Openbare resultaten en beheerfuncties moeten van elkaar worden gescheiden.

De huidige app is niet ingericht voor rechtstreekse publicatie op het internet. Een iframe in WordPress lost hosting en beveiliging niet op; het is alleen een manier om een al bereikbare pagina in te sluiten.

**Voordeel:** een centrale online toepassing, met mogelijkheden voor actuele standen.

**Nadeel:** de grootste wijziging en blijvend technisch beheer. Gewone WordPress-hosting ondersteunt niet noodzakelijk een Django-app.

## Advies

Houd de app voorlopig lokaal en publiceer alleen de gewenste resultaten naar WordPress. De competitiecomputer hoeft dan niet permanent online te blijven en beheerfuncties worden niet publiek toegankelijk.

- Gebruik de beschikbare kopieerfunctie als handmatig publiceren na elke speeldag volstaat.
- Kies **optie 2** als de beheerder met een knop de websitepagina's wil bijwerken.
- Kies **optie 3** alleen wanneer er ook behoefte is aan een volwaardige online competitieapp.

Gebruik bij export of publicatie de bestaande berekeningen uit de app. WordPress toont de resultaten en hoeft de puntentelling niet opnieuw te implementeren. Publiceer alleen gegevens die voor de publieke website bedoeld zijn, niet de volledige SQLite-database.

Er is nog geen keuze gemaakt of koppeling geconfigureerd.