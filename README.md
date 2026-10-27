# The Stallion Bullets

Lokale webapp voor het beheren van de dartscompetitie. De applicatie gebruikt Django en bewaart alle gegevens in het SQLite-bestand `competitie.sqlite3` in deze projectmap.

## Opstarten op Windows

Open PowerShell in deze map en voer uit:

```powershell
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open daarna <http://127.0.0.1:8000>.

Om de app bereikbaar te maken op apparaten op hetzelfde wifi-netwerk:

```powershell
python manage.py runserver 0.0.0.0:8000
```

Zoek op de laptop het lokale IPv4-adres met `ipconfig`; open op een ander apparaat `http://<lokaal-ip-adres>:8000`. Sta Python eventueel toe in Windows Firewall voor het privé-netwerk. Deze eerste versie heeft geen gebruikersaccounts en is bedoeld voor een vertrouwd lokaal netwerk, niet voor rechtstreekse publicatie op het internet.

## Gebruik

1. Maak een seizoen aan.
2. Beheer spelers via **Spelers**; bestaande namen kun je daar aanpassen of inactief maken. Na een naamwijziging blijven eerdere avonden en statistieken aan dezelfde speler gekoppeld.
3. Maak een competitieavond, voer de datum in als `dd/MM/yyyy`, kies 2 tot en met 30 dartsblokken, stel 1 tot en met 20 wedstrijden per speler in (standaard 5) en vink alleen de aanwezige spelers aan. De aanvinkvolgorde is de lotingsvolgorde.
4. Een avond ondersteunt 4 tot en met 128 spelers. Elke speler krijgt het ingestelde aantal wedstrijden, inclusief een eventuele stromanwedstrijd. Het schema gebruikt verschillende tegenstanders waar mogelijk; bij kleine spelersaantallen of veel wedstrijden kunnen tegenstanders terugkeren.
5. Per ronde worden alle blokken tegelijk gebruikt waar spelersaantal en scheidsrechterbeschikbaarheid dit toelaten. Elke speler kan maximaal één wedstrijd per ronde spelen. Alleen de laatste ronde kan minder wedstrijden bevatten als het totaal niet deelbaar is door het aantal bruikbare blokken. Een extra stromanwedstrijd staat in die laatste ronde of als laatste wedstrijd.
6. Druk wedstrijdbriefjes af vanaf de avondpagina. Per wedstrijd wordt één briefje afgedrukt.
7. Vul of corrigeer een resultaat via **Invullen/Bewerken**. Punten en klassementen worden direct opnieuw berekend.
8. Een avond zonder ingevoerde uitslagen kun je via **Schema opnieuw opmaken** opnieuw laten plannen; dit vervangt de bestaande wedstrijdrecords. Na het invoeren van een uitslag/statistiek is opnieuw opmaken geblokkeerd.
9. Een avond verwijder je vanaf de avondpagina. De app vraagt eerst om bevestiging; daarna worden de bijbehorende wedstrijden, uitslagen en aanwezigheid verwijderd.

Elk gewonnen leg is één punt. Iedere 171-, 174-, 177- of 180-worp, elke ingevoerde finish van 100 tot en met 170 en elke leg in maximaal 15 pijlen leveren elk één bonuspunt op. Vul de pijlen per leg komma-gescheiden in, bijvoorbeeld `13, 15`. De stroman krijgt geen eigen klassementspunten.

Maak een back-up door de app te stoppen en `competitie.sqlite3` te kopiëren. Bewaar ook de projectbestanden en het clublogo.

## Tests

```powershell
python manage.py test bullets
```
