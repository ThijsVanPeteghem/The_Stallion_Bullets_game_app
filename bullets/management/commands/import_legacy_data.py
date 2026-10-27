from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from bullets.legacy_import import (
    LegacyImportError,
    apply_player_aliases,
    import_legacy_evenings,
    parse_legacy_file,
)


class Command(BaseCommand):
    help = "Importeer legacy speeldagbestanden in de geselecteerde database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            default=str(settings.BASE_DIR / "old_format_data"),
            help="Bestand of map met speeldagN__dd-mm-jjjj.txt bestanden.",
        )
        parser.add_argument(
            "--season",
            default="2026-2027",
            help="Naam van het seizoen waarin de avonden worden geplaatst.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Valideer en toon de import zonder gegevens op te slaan.",
        )
        parser.add_argument(
            "--alias",
            action="append",
            default=[],
            metavar="BRONNAAM=NAAM",
            help="Koppel een afwijkende spelersnaam aan de juiste naam; herhaalbaar.",
        )

    def handle(self, *args, **options):
        source = Path(options["source"])
        if source.is_dir():
            paths = sorted(source.glob("speeldag*.txt"))
        elif source.is_file():
            paths = [source]
        else:
            raise CommandError(f"Bronbestand of map bestaat niet: {source}")
        if not paths:
            raise CommandError(f"Geen speeldagbestanden gevonden in {source}.")

        try:
            parsed = [parse_legacy_file(path) for path in paths]
        except LegacyImportError as error:
            raise CommandError(str(error)) from error
        parsed.sort(key=lambda item: item["date"])

        if len({item["date"] for item in parsed}) != len(parsed):
            raise CommandError("De bronbestanden bevatten dubbele speeldagdatums.")
        aliases = {}
        for alias in options["alias"]:
            if "=" not in alias:
                raise CommandError(
                    f"Ongeldige alias {alias!r}; gebruik BRONNAAM=NAAM."
                )
            source_name, target_name = (
                part.strip() for part in alias.split("=", 1)
            )
            if not source_name or not target_name:
                raise CommandError(
                    f"Ongeldige alias {alias!r}; beide namen zijn verplicht."
                )
            aliases[source_name] = target_name
        if aliases:
            parsed = apply_player_aliases(parsed, aliases)

        self.stdout.write("Gevalideerde bestanden:")
        for item in parsed:
            self.stdout.write(
                f"- {item['name']}: {len(item['players'])} spelers, "
                f"{len(item['matches'])} wedstrijden, "
                f"{item['match_count']} reguliere wedstrijden per speler, "
                f"stroman: {item['stroman']} (+1 wedstrijd)"
            )
        self.stdout.write(
            f"Seizoen: {options['season']}; database: {settings.DATABASES['default']['NAME']}"
        )
        for source_name, target_name in aliases.items():
            self.stdout.write(f"Naamkoppeling: {source_name} -> {target_name}")
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry-run: er zijn geen gegevens opgeslagen."))
            return

        try:
            imported = import_legacy_evenings(parsed, options["season"])
        except LegacyImportError as error:
            raise CommandError(str(error)) from error

        for evening in imported:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Geïmporteerd: {evening.date:%d-%m-%Y} "
                    f"({evening.matches.count()} wedstrijden)."
                )
            )
