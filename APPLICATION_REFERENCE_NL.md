# The Stallion Bullets — applicatie- en spelreferentie

**Doel:** dit document beschrijft het waarneembare gedrag en de spelregels van de huidige applicatie. Gebruik het als basis voor handmatige controles en toekomstige pipeline-validatie op regressies en afwijkingen.

**Bron van waarheid:** waar dit document spreekt over de huidige werking, zijn de implementatie en tests leidend. Een expliciet gemarkeerd aandachtspunt is geen bevestigde gewenste regel; laat dat eerst door de competitie-organisatie beslissen. De regels kunnen veranderen wanneer de software verandert.

## 1. In één oogopslag

The Stallion Bullets is een lokale Django-webapp voor het beheren van dartscompetities. De beheerder maakt seizoenen en spelers aan, registreert aanwezigen voor een competitieavond, laat de wedstrijden plannen, drukt wedstrijdbriefjes af en voert uitslagen en statistieken in. De app berekent avond- en seizoensklassementen.

| Onderdeel | Huidige werking |
|---|---|
| Webframework | Django 5.2 of hoger, maar lager dan 6.0 |
| Database | SQLite, bestand `competitie.sqlite3` in de projectmap |
| Taal en tijdzone | `nl-be`, `Europe/Brussels` |
| Gebruikersaccounts | Niet aanwezig |
| Applicatieonderdelen | Seizoenen, spelers, competitieavonden, wedstrijdschema, uitslagen, statistieken, klassementen en printbriefjes |
| Afhankelijkheden voor bedrijfslogica | Vooral [bullets/models.py](./bullets/models.py), [bullets/forms.py](./bullets/forms.py), [bullets/schedule.py](./bullets/schedule.py), [bullets/services.py](./bullets/services.py) en [bullets/views.py](./bullets/views.py) |

De applicatie is bedoeld voor vertrouwd lokaal gebruik. De project-README waarschuwt tegen rechtstreekse publicatie op internet.

## 2. Schermen en gebruikersstromen

### Startpagina

Toont seizoenen, het aantal avonden per seizoen en maximaal acht recente avonden. Vanaf hier kan een beheerder een avond, seizoen of speler aanmaken/beheren.

### Seizoenen

- Een seizoen heeft een unieke naam van maximaal 80 tekens.
- De lijst en startpagina linken door naar de avonden en het klassement van een seizoen.
- Er is geen seizoensverwijderactie in de interface.
- Verwijderen van een seizoen zou volgens de gegevensrelatie de avonden en de daarbij horende gegevens verwijderen; dit is geen beschikbare schermactie.

### Spelers

- Een speler heeft een unieke naam van maximaal 100 tekens en een actieve/inactieve status.
- Namen worden in het formulier ook hoofdletterongevoelig op duplicaten gecontroleerd.
- Alleen actieve spelers kunnen voor een nieuwe avond worden geselecteerd.
- Een speler kan inactief worden gemaakt in plaats van te worden verwijderd. De bestaande statistieken en verwijzingen blijven zo bij dezelfde speler horen.
- Een naamwijziging verandert de getoonde naam van die speler ook in historische wedstrijd- en klassementgegevens; het maakt geen nieuwe speler aan.

### Nieuwe competitieavond

De beheerder kiest een seizoen, datum, gevraagd aantal dartsblokken, aantal wedstrijden per speler en de aanwezige spelers.

- Datumformaat in het formulier: `dd/MM/yyyy`.
- Dartsblokken: minimaal 2, maximaal 30; beginwaarde 4.
- Wedstrijden per speler: minimaal 1, maximaal 20; beginwaarde 5.
- Aanwezig: minimaal 4, maximaal 128 actieve spelers.
- De volgorde waarin spelers worden aangevinkt, wordt vastgelegd als lotingsvolgorde. De server controleert dat de lijst alle en uitsluitend geselecteerde spelers precies eenmaal bevat.
- Na opslaan maakt de app de aanwezigheid, wedstrijden en een lege statistiekregel per echte wedstrijddeelnemer aan.

### Avondpagina en tussenstand

De avondpagina toont het schema, de ronde en het blok, tegenstanders, scheidsrechter, uitslagstatus en links om uitslagen in te voeren of te corrigeren. De controletabel toont voor iedere aanwezige het aantal ingeplande wedstrijden en scheidsrechterbeurten.

De tussenstand van een avond toont de klassementgegevens zonder het wedstrijdschema. Een wedstrijd is voltooid als voor iedere verwachte deelnemer een statistiekregel bestaat en het aantal gewonnen legs is ingevuld. Alleen een voltooid duel draagt de ingevoerde statistieken en punten bij aan de klassementberekening.

### Wedstrijdbriefjes

De printpagina toont één afdrukbaar briefje per geplande wedstrijd met datum, ronde, blok, wedstrijdnummer, spelers, legs, 171/174/177/180, aantal high finishes, minste pijlen en scheidsrechter. Via de afdrukknop wordt de browserafdruk gestart. Bij een stromanwedstrijd staat “Stroman” als tegenstander.

### Schema opnieuw opmaken en avond verwijderen

- Een schema kan opnieuw worden gemaakt zolang er geen uitslag of statistiek is ingevoerd. De actie vervangt de bestaande wedstrijdrecords.
- Zodra een uitslag of een van de statistieken is ingevuld, blokkeert de server opnieuw plannen. Alleen de knop verbergen is dus niet de enige bescherming.
- Een avond verwijderen vereist een bevestigingspagina en een POST-bevestiging. De avond, bijbehorende wedstrijden, statistieken en aanwezigheidsregistraties worden verwijderd; het seizoen blijft bestaan.

## 3. Wedstrijdplanning: regels en invarianten

### Aantal wedstrijden

Iedere aanwezige krijgt het ingestelde aantal wedstrijden, inclusief een eventuele wedstrijd tegen de stroman. Het totale aantal wedstrijden is:

```text
ceil(aantal spelers × wedstrijden per speler / 2)
```

De afronding naar boven is nodig wanneer het product oneven is. Bij zo'n geval kan een wedstrijd een stroman bevatten, die geen echte speler is.

### Ronden, blokken en rust

- Een speler speelt maximaal één wedstrijd per ronde.
- In een ronde speelt een scheidsrechter niet zelf in een wedstrijd van diezelfde ronde.
- Binnen een ronde wordt een speler niet meer dan eenmaal als scheidsrechter toegewezen.
- Het aantal werkelijk gebruikte blokken kan kleiner zijn dan het gevraagde aantal. De planner begrenst dat mede op basis van het aantal beschikbare spelers en wedstrijden; vraag dus niet aan een validatiepipeline om altijd precies het aangevraagde aantal blokken te zien.
- De planner probeert ronden zo volledig mogelijk te vullen. Als het aantal wedstrijden niet deelbaar is door het bruikbare aantal blokken, kan de laatste ronde gedeeltelijk gevuld zijn.
- Voor een geldige scheidsrechtertoewijzing gebruikt de planner de spelers van de vorige wedstrijd op hetzelfde blok als kandidaten. Daardoor is de scheidsrechterbeurt gekoppeld aan de blokroulatie.
- De planner probeert scheidsrechterbeurten evenwichtig over aanwezigen te verdelen. Tests verwachten in gecontroleerde gevallen maximaal één verschil tussen het hoogste en laagste aantal beurten; dit is een geteste uitkomst, geen garantie dat ieder denkbaar invoergeval identieke verdeling oplevert.
- De planner probeert tegenstanders te variëren, maar herhaling is toegestaan en kan bij een kleine spelersgroep of veel wedstrijden voorkomen.
- Exacte wedstrijden, bloknummers, ronden en loting zijn niet de stabiele interface. Valideer primair de invarianten hierboven, niet één willekeurige exacte planning.

### Stroman

De stroman is een virtuele tegenstander: er is geen tweede spelerrecord of eigen klassement. Een stromanwedstrijd telt wel als wedstrijd voor de echte speler.

**Huidige implementatieregel:** een stromanwedstrijd ontstaat wanneer zowel het aantal spelers als het ingestelde aantal wedstrijden per speler oneven is. De gegenereerde planning bevat dan één stromanwedstrijd. De stromanwedstrijd krijgt één echte deelnemer en één scheidsrechter; het schema plaatst de wedstrijd als laatste of in de laatste ronde.

**Aandachtspunt voor productvalidatie:** de planner maakt de stromanwedstrijd aan voor spelerindex `0`, dus de eerste speler in lotingsvolgorde. De interface vermeldt dat de stroman bij vijf spelers rouleert. Dat kan betekenen dat de stroman over verschillende avonden rouleert via wisselende lotingsvolgorde, maar de planner roteert hem niet tussen spelers binnen één avond. Bevestig met de competitie-organisatie wat “rouleren” precies betekent voordat een pipeline dit als gewenste regel afdwingt.

## 4. Uitslag- en statistiekregels

Per echte speler per wedstrijd worden legs, aantallen speciale worpen, high finishes en pijlen per leg ingevoerd.

### Legs

- Een wedstrijd wordt als voltooid beschouwd zodra de legs voor alle betrokken echte spelers zijn ingevuld.
- Bij een gewone wedstrijd moeten de legs van beide spelers samen exact 3 zijn.
- Iedere legs-invoer ligt tussen 0 en 3.
- Een correctie overschrijft de eerdere invoer; klassementen worden uit de opgeslagen records opnieuw berekend.
- Voor een stromanwedstrijd vult men alleen de legs van de echte speler in. De virtuele tegenstander heeft geen invoerveld of statistiekrecord.
- Voor de stromanwedstrijd leidt de klassementlogica de legs van de virtuele tegenstander af als `3 - legs van de echte speler`.

### Bonusstatistieken en punten

De punten van een speler in een voltooide wedstrijd zijn:

```text
gewonnen legs
+ aantal 180-worpen
+ aantal 177-worpen
+ aantal 174-worpen
+ aantal 171-worpen
+ aantal ingevoerde high finishes
+ aantal ingevoerde legs in maximaal 15 pijlen
```

Elk onderdeel telt per gebeurtenis één bonuspunt; een high finish is dus één punt per finish, niet één punt per finishwaarde. De stroman krijgt geen eigen punten of klassement.

Validatie van invoer:

- Aantallen 171/174/177/180 zijn gehele getallen vanaf 0.
- Een high finish is een komma-gescheiden waarde van 100 t/m 170. Leeg is toegestaan.
- “Minste pijlen” is een komma-gescheiden lijst van maximaal drie waarden, elk van 1 t/m 15. Leeg is toegestaan. Voorbeelden: `13` en `13, 15`.
- Ongeldige tekst, waarden buiten de grenzen of meer dan drie pijlenwaarden worden door het formulier afgewezen.
- Een invoerwaarde voor minste pijlen staat voor een leg; deze invoer verhoogt het aantal bonuspunten met één per opgegeven waarde.

## 5. Klassementen en betekenis van kolommen

Het avond- en seizoensklassement bevat:

- **Punten:** legs plus bonuspunten uit voltooide wedstrijden.
- **Matchen:** aantal statistiekregels dat in voltooide wedstrijden is meegeteld. Een niet-voltooide wedstrijd telt niet mee.
- **W-V:** gewonnen en verloren wedstrijden. Een gewone partij wordt beslist door de ingevoerde legverhouding. Een stromanpartij wordt beslist door de vergelijking van de echte speler met de afgeleide drie legs.
- **Legs +/−:** legs voor en tegen; bij een stromanpartij telt de afgeleide score van de virtuele speler als tegen-legs.
- **HF:** hoogste ingevoerde finish en tussen haakjes het totale aantal geregistreerde high finishes.
- **Hoogste worp:** hoogste categorie met ten minste één worp uit 180, 177, 174 en 171. Dit is dus de hoogste van deze vier categorieën waarvoor een aantal is geregistreerd.
- **Min. pijlen:** laagste geldige ingevoerde pijlenwaarde over alle voltooide wedstrijden.
- **Scheids:** aantal ingeplande scheidsrechterbeurten. Dit wordt geteld uit het schema, ook als de bijbehorende wedstrijd nog geen uitslag heeft.

Seizoenstand bevat spelers die in ten minste één avond aanwezig waren. De sortering is:

1. punten aflopend;
2. legs voor aflopend;
3. legs tegen oplopend;
4. naam hoofdletterongevoelig oplopend.

De klassementlogica wordt geïmplementeerd in [bullets/services.py](./bullets/services.py); de kolommen worden getoond in [standings_table.html](./bullets/templates/bullets/standings_table.html).

## 6. Gegevensmodel en verwijdergedrag

| Gegeven | Relatie / levenscyclus |
|---|---|
| Seizoen | Heeft competitieavonden; naam is uniek. |
| Speler | Kan meerdere avonden, wedstrijden, statistieken en scheidsrechterbeurten hebben. Inactief zetten behoudt historie. |
| Avond | Hoort bij één seizoen en bewaart datum, gevraagd aantal blokken en aantal wedstrijden per speler. |
| Aanwezigheid | Koppelt één speler aan één avond en bewaart lotingsnummer. De speler en lotingsnummers zijn per avond uniek. |
| Wedstrijd | Hoort bij één avond; bewaart wedstrijdnummer, ronde, blok, twee echte spelers (waarbij de tweede ontbreekt bij een stromanwedstrijd) en optionele scheidsrechter. |
| Spelerstatistiek | Eén record per speler per wedstrijd; legs kunnen nog leeg zijn zolang de uitslag niet is ingevuld. |

Avond verwijderen verwijdert de avondafhankelijke wedstrijd- en aanwezigheidsgegevens. Spelers worden door bestaande relaties beschermd tegen verwijderen zolang zij historisch gebruikt zijn. Een seizoen verwijderen is cascadegedrag in het model, maar heeft geen gebruikersactie in de huidige interface.

## 7. Validatiechecklist voor regressiepipelines

Gebruik dit als functionele acceptatiechecklist. Een pipeline moet waar mogelijk per regel een testresultaat en concrete afwijking rapporteren; verander de verwachte regel niet stilzwijgend op basis van toeval in de planning.

### Invoer en beheer

- [ ] Seizoensnaam is uniek en maximaal 80 tekens.
- [ ] Spelersnaam is uniek (formuliercontrole hoofdletterongevoelig) en maximaal 100 tekens.
- [ ] Inactieve spelers zijn niet selecteerbaar bij een nieuwe avond; historische gegevens blijven zichtbaar.
- [ ] Avond accepteert alleen 4–128 geselecteerde actieve spelers.
- [ ] Avond accepteert alleen 2–30 gevraagde blokken en 1–20 wedstrijden per speler.
- [ ] Ongeldige datum of lotingslijst maakt geen avond aan.
- [ ] Lotingsnummers zijn uniek en stemmen overeen met de aangeleverde aanvinkvolgorde.

### Planning

- [ ] Totaal geplande wedstrijden volgt `ceil(spelers × wedstrijden_per_speler / 2)`.
- [ ] Elke aanwezige komt precies het ingestelde aantal keer voor als echte speler, inclusief eventuele stromanwedstrijd.
- [ ] Geen echte speler speelt meer dan één keer in dezelfde ronde.
- [ ] Geen scheidsrechter speelt in dezelfde ronde; geen scheidsrechter krijgt meer dan één wedstrijd per ronde.
- [ ] Per aanwezige is het ingeplande aantal wedstrijden gelijk aan de ingestelde waarde.
- [ ] Gebruikte bloknummers zijn positief, aaneengesloten vanaf 1 en niet groter dan het gevraagde aantal.
- [ ] Een ronde is zo vol mogelijk binnen de beschikbare blokken; een rest kan de laatste ronde verkleinen.
- [ ] Bij oneven spelersaantal én oneven wedstrijdaantal bestaat precies één stromanwedstrijd; bij overige combinaties bestaat die niet.
- [ ] Scheidsrechterbeurten zijn gecontroleerd op evenwicht, maar valideer de grens op basis van ondersteunde scenario's, niet op een veronderstelde identieke verdeling.
- [ ] Tegenstanderherhaling is alleen een fout als een expliciete productregel dat verbiedt; de huidige applicatie staat herhaling toe.
- [ ] Controleer de stromanverdeling apart en stem de interfaceclaim (“rouleert”) af op de gewenste competitiepraktijk.

### Uitslagen en klassement

- [ ] Een gewone wedstrijd accepteert uitsluitend legs die samen exact 3 zijn; beide waarden liggen tussen 0 en 3.
- [ ] Onvolledige wedstrijdgegevens tellen niet mee voor punten, matchen, legs, uitslagen of bonusstatistieken.
- [ ] Iedere geldige 171/174/177/180, high finish en ≤15-pijlenleg levert precies één bonuspunt op.
- [ ] High finishes zijn alleen 100–170; pijlenwaarden zijn alleen 1–15 en maximaal drie per speler per wedstrijd.
- [ ] Een uitslagcorrectie vervangt eerdere waarden en veroorzaakt geen dubbele punten.
- [ ] Een stroman heeft geen eigen record of punten; de virtuele score wordt alleen voor de echte speler als legs-tegen/-verhouding gebruikt.
- [ ] Seizoensstand bevat alleen spelers met avonddeelname en sorteert op de vier vastgelegde criteria.
- [ ] Scheidsrechterbeurten in het klassement tellen uit het schema, onafhankelijk van voltooiing van de uitslag.

### Acties en gegevensbehoud

- [ ] Een avond zonder ingevulde uitslagen/statistieken kan opnieuw worden gepland; oude wedstrijdrecords worden vervangen.
- [ ] Een avond met enige ingevoerde uitslag of statistiek kan niet opnieuw worden gepland.
- [ ] Avond verwijderen vraagt bevestiging en verwijdert wedstrijd-, statistiek- en aanwezigheidsgegevens, maar niet het seizoen.
- [ ] Na een spelersnaamwijziging blijven oude statistieken en wedstrijden aan dezelfde speler gekoppeld.
- [ ] Wedstrijdbriefjes bevatten één briefje per wedstrijd en de relevante reeds opgeslagen gegevens.

## 8. Bekende aandachtspunten en regels die niet moeten worden verondersteld

1. **Stromanroulatie:** de gebruikersinterface suggereert roulatie bij vijf spelers; de schemafunctie gebruikt de eerste speler in de lotingsvolgorde voor de stromanwedstrijd. Dit vraagt een productbesluit (zie §3).
2. **Stroman-scorevalidatie:** voor gewone wedstrijden is de som van legs expliciet gevalideerd. Voor een stromanwedstrijd wordt alleen de waarde 0–3 voor de echte speler gevalideerd; de virtuele score wordt rekenkundig `3 - echte_legs`. De invoervalidatie verhindert dus niet zelf iedere mogelijk onrealistische uitkomst. Beslis of een aanvullende regel gewenst is voordat een pipeline daar een verwachting van maakt.
3. **Schema-exactheid:** de planner gebruikt heuristiek, meerdere pogingen voor kleine groepen en een vaste seed-afleiding. Niet alle geldige roosterkeuzes zijn een contract. Valideer invarianten en geen specifieke paringen.
4. **Tegenstanders:** herhaalde tegenstanders zijn uitdrukkelijk mogelijk bij kleine groepen of veel wedstrijden.
5. **Aanwezigheid en klassement:** een speler die niet op een avond aanwezig is, krijgt voor die avond geen nulscore-record; klassementen zijn opgebouwd uit geregistreerde deelnames en voltooide wedstrijden.
6. **Beveiligde publicatie:** er zijn geen accounts; instellingen bevatten `DEBUG = True` en een ontwikkelsleutel. Dit referentiedocument is geen deployment- of beveiligingsgoedkeuring. Stel de applicatie niet publiek bloot op basis van alleen deze handleiding.

## 9. Lokale uitvoering en tests

Project-README:

```powershell
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open vervolgens `http://127.0.0.1:8000`. Bestaande functionele tests draaien met:

```powershell
python manage.py test bullets
```

De plannings- en flowtests staan in [bullets/tests.py](./bullets/tests.py). De routekaart staat in [bullets/urls.py](./bullets/urls.py). Voor een back-up adviseert de README de app te stoppen en `competitie.sqlite3` te kopiëren; bewaar ook de projectbestanden en het clublogo.

## 10. Bronnen in de code

- Gegevensmodel en puntberekening: [bullets/models.py](./bullets/models.py)
- Formulier- en invoerregels: [bullets/forms.py](./bullets/forms.py)
- Wedstrijdplanning: [bullets/schedule.py](./bullets/schedule.py)
- Avondcreatie, opnieuw plannen en klassementberekening: [bullets/services.py](./bullets/services.py)
- Pagina-acties: [bullets/views.py](./bullets/views.py)
- Regressietests: [bullets/tests.py](./bullets/tests.py)
- Start-, netwerk- en gebruiksinstructies: [README.md](./README.md)
