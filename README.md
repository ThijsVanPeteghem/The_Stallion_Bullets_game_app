# The Stallion Bullets

Lokale webapp voor het beheren van de dartscompetitie. De applicatie gebruikt Django en bewaart de gegevens standaard in het SQLite-bestand `competitie.sqlite3` in deze projectmap. Met de omgevingsvariabele `DATABASE_NAME` kun je een andere database kiezen.

## Opstarten op Windows

Dubbelklik in de projectmap op een van deze bestanden:

- **Start sandbox.bat**: opent de sandbox met een aparte database (`competitie-sandbox.sqlite3`). Gegevens hierin veranderen de echte competitie niet.
- **Start competitie.bat**: opent de competitie met de bestaande database (`competitie.sqlite3`).
- **Database archiveren.bat**: maakt met één dubbelklik een datum/tijd-snapshot van de competitie- of sandboxdatabase in `database_snapshots`. Je kunt de app hiervoor open laten.
- **Database verwijderen.bat**: verwijdert na expliciete bevestiging de gekozen competitie- of sandboxdatabase. Stop de app eerst; verwijderen is definitief.

Bij de eerste start installeert het script zo nodig de benodigde Python-onderdelen. Daarna wordt de database bijgewerkt en opent de applicatie vanzelf in de browser. Laat het zwarte venster open zolang je de applicatie gebruikt; sluit de app met `Ctrl+C` in dat venster. Start niet beide tegelijk, want ze gebruiken hetzelfde webadres.

De scripts verwachten Python 3. Als Python nog niet is geïnstalleerd, installeer het dan via <https://www.python.org/downloads/> en probeer opnieuw.

Je kunt de applicatie ook handmatig starten vanuit PowerShell in deze map:

```powershell
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open daarna <http://127.0.0.1:8000>.

## Verschillende databases gebruiken

Kies per PowerShell-venster de database voordat je Django-commando's uitvoert. Een relatieve bestandsnaam wordt opgeslagen in de projectmap; je kunt ook een volledig pad opgeven.

Gebruik bijvoorbeeld een aparte database om te testen:

```powershell
$env:DATABASE_NAME = "competitie-test.sqlite3"
python manage.py migrate
python manage.py runserver
```

In datzelfde PowerShell-venster gebruiken ook andere Django-commando's, zoals `createsuperuser` en `migrate`, deze testdatabase. De app maakt het databasebestand aan wanneer dat nodig is. Sluit het venster of voer dit uit om terug te keren naar de standaarddatabase `competitie.sqlite3`:

```powershell
Remove-Item Env:DATABASE_NAME
```

Je kunt meerdere testdatabases maken met verschillende namen, bijvoorbeeld `competitie-acceptatie.sqlite3`. Houd de productie-instelling apart en expliciet, bijvoorbeeld in een eigen productie-startscript of de omgevingsinstellingen van de server:

```powershell
$env:DATABASE_NAME = "C:\data\competitie-productie.sqlite3"
python manage.py migrate
python manage.py runserver
```

Voer `migrate` voor elke database uit die je gebruikt. Django's automatische test-runner maakt voor `python manage.py test` een aparte, tijdelijke testdatabase aan op basis van de gekozen instellingen. Gebruik geen productiegegevens in een testkopie zonder die eerst te anonimiseren.

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

Elk gewonnen leg is één punt, behalve voor een speler die als stroman is gemarkeerd. Een 180- of 171-worp levert één punt op. Een finish van 100–160 levert één punt op; finishes van 161, 164, 167 en 170 leveren twee punten op. Minste pijlen levert geen bonuspunten op. De stroman krijgt geen punten voor legs, maar wel voor geldige worpen en finishes. 174- en 177-worpen worden niet meer ingevoerd of getoond; eerder opgeslagen gegevens blijven behouden.

Maak een back-up door de app te stoppen en `competitie.sqlite3` te kopiëren. Bewaar ook de projectbestanden en het clublogo.

Voor terug te vinden tijdsnapshots dubbelklik je op **Database archiveren.bat** en kies je competitie of sandbox. Een snapshot wordt onder `database_snapshots` bewaard met database- en tijdstempel in de bestandsnaam. Het script gebruikt SQLite's online-back-upfunctie, controleert de integriteit en overschrijft bestaande snapshots niet. Snapshots worden niet automatisch verwijderd; bewaar periodiek ook een kopie buiten deze computer.

Om een database opnieuw te beginnen, stop je de app, start je **Database verwijderen.bat**, kies je de competitie- of sandboxdatabase en typ je `DELETE`. Bij de volgende start maakt Django een lege database aan en voert het de migraties uit.

### Oude speeldagen importeren

De twee tekstbestanden in `old_format_data` kunnen na het migreren van de database met dit commando worden geïmporteerd. Controleer eerst de bronbestanden zonder iets op te slaan:

```powershell
python manage.py migrate
python manage.py import_legacy_data --dry-run
```

Voer de import daarna uit in de gekozen database:

```powershell
python manage.py import_legacy_data
```

De import maakt seizoen `2026-2027`, spelers, aanwezigheden, wedstrijdschema's, schrijvers, uitslagen en statistieken aan. De stromanmarkering wordt overgenomen; legs van die speler leveren geen punten op, de geregistreerde worpen en finishes blijven meetellen. De import stopt als een speeldag met dezelfde datum al bestaat. Bronbestanden worden niet aangepast.

Bij een bekende schrijfvariant kan een expliciete naamkoppeling worden meegegeven, bijvoorbeeld:

```powershell
python manage.py import_legacy_data --alias "Oude naam=Juiste naam"
```

## Tests

```powershell
python manage.py test bullets
```
