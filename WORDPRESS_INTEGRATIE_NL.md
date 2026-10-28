# Resultaten publiceren op de WordPress-clubwebsite

Datum: 28 oktober 2026

## Doel en huidige situatie

De competitiebeheerder beheert de clubwebsite via WordPress:
https://thestallionbullets.be/

Op de competitiepagina staan aparte links naar speeldaguitslagen, het klassement, hoogste finishes en 180-worpen:
https://thestallionbullets.be/maandelijkse-competitie/

De Django-webapp berekent de resultaten en klassementen al. Ze draait momenteel lokaal en heeft geen gebruikersaccounts. Er is nog geen exportfunctie of WordPress-koppeling ingebouwd. Onderstaande opties zijn voorstellen, geen beschikbare functies.

## Optie 1: exporteren en plakken

Voeg een knop **Kopieren voor WordPress** toe voor speeldagresultaten en seizoensklassementen.

Werkwijze voor de beheerder:

1. Voer de resultaten in de app in.
2. Kopieer de gewenste tabel.
3. Plak de tabel in de juiste WordPress-pagina en werk die bij.

Dit vraagt geen automatische koppeling of extra hosting. Vooraf moet worden getest hoe de gebruikte WordPress-editor de tabellen overneemt. Een CSV-export voor een tabelplugin zoals TablePress is een alternatief; de importmogelijkheden hangen af van de gebruikte plugin en versie.

**Voordeel:** eenvoudig te realiseren en geen toegang tot WordPress nodig vanuit de app.

**Nadeel:** de beheerder moet de tabellen na iedere speeldag of correctie handmatig overzetten.

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

- Kies **optie 1** als handmatig publiceren na elke speeldag volstaat.
- Kies **optie 2** als de beheerder met een knop de websitepagina's wil bijwerken.
- Kies **optie 3** alleen wanneer er ook behoefte is aan een volwaardige online competitieapp.

Gebruik bij export of publicatie de bestaande berekeningen uit de app. WordPress toont de resultaten en hoeft de puntentelling niet opnieuw te implementeren. Publiceer alleen gegevens die voor de publieke website bedoeld zijn, niet de volledige SQLite-database.

Er is nog geen keuze gemaakt of koppeling geconfigureerd.