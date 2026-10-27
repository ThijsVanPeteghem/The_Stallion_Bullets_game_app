from contextlib import closing
from datetime import datetime
import os
from pathlib import Path
import sqlite3
from uuid import uuid4


def create_database_snapshot(database_path, output_dir, timestamp=None):
    database_path = Path(database_path)
    output_dir = Path(output_dir)
    if not database_path.is_file():
        raise FileNotFoundError(f"Databasebestand niet gevonden: {database_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = timestamp or datetime.now()
    timestamp_text = timestamp.strftime("%Y%m%d_%H%M%S")
    base_name = f"{database_path.stem}_{timestamp_text}"
    snapshot_path = output_dir / f"{base_name}.sqlite3"
    suffix = 2
    while snapshot_path.exists():
        snapshot_path = output_dir / f"{base_name}_{suffix:02}.sqlite3"
        suffix += 1

    temporary_path = output_dir / f".{uuid4().hex}.tmp.sqlite3"
    try:
        with closing(sqlite3.connect(str(database_path))) as source:
            with closing(sqlite3.connect(str(temporary_path))) as destination:
                source.backup(destination)
                result = destination.execute("PRAGMA integrity_check").fetchone()
                if result != ("ok",):
                    raise sqlite3.DatabaseError(
                        f"Snapshotintegriteitscontrole mislukt: {result!r}"
                    )
        os.replace(temporary_path, snapshot_path)
    except (OSError, sqlite3.Error):
        temporary_path.unlink(missing_ok=True)
        raise
    return snapshot_path
