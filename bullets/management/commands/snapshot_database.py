from pathlib import Path
import sqlite3

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from bullets.snapshots import create_database_snapshot


class Command(BaseCommand):
    help = "Maak een controleerbare tijdstempel-snapshot van de geselecteerde SQLite-database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            default="default",
            help="Django database-alias die moet worden gearchiveerd.",
        )
        parser.add_argument(
            "--output-dir",
            default=str(settings.BASE_DIR / "database_snapshots"),
            help="Map waarin het snapshotbestand wordt opgeslagen.",
        )

    def handle(self, *args, **options):
        alias = options["database"]
        databases = settings.DATABASES
        if alias not in databases:
            raise CommandError(f"Onbekende database-alias: {alias}")
        config = databases[alias]
        if config["ENGINE"] != "django.db.backends.sqlite3":
            raise CommandError("Snapshots worden alleen ondersteund voor SQLite-databases.")
        database_path = Path(config["NAME"])
        if not database_path.is_absolute():
            database_path = settings.BASE_DIR / database_path

        try:
            snapshot_path = create_database_snapshot(
                database_path,
                options["output_dir"],
            )
        except (OSError, sqlite3.Error) as error:
            raise CommandError(f"Database snapshot mislukt: {error}") from error

        self.stdout.write(self.style.SUCCESS(f"Database gearchiveerd: {snapshot_path}"))
