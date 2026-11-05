# Korte go-live preflight checklist

1. **Backup maken**  
   Kopieer `data/competitie.sqlite3` naar een backupbestand met datum/tijd.

2. **App starten**  
   In `scripts/`:
   ```bash
   python manage.py runserver 0.0.0.0:8000
   ```

3. **Snelle functionele check**  
   - Open `http://localhost:8000`
   - Open `http://localhost:8000/spelers/`
   - Vul 1 wedstrijd in en controleer dat tussenstand automatisch ververst.

4. **Tijdens de avond**  
   1 persoon invoer laten doen, tweede scherm/tab op tussenstand laten staan.

5. **Rollback bij probleem**  
   - Server stoppen (`CTRL+C`)
   - Backup terugzetten naar `data/competitie.sqlite3`
   - Server opnieuw starten.

6. **Na afloop**  
   Opnieuw backup maken van `data/competitie.sqlite3`.
