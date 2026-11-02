from collections import Counter

from django.db import migrations


def repair_legacy_block_rounds(apps, schema_editor):
    Evening = apps.get_model("bullets", "Evening")
    Match = apps.get_model("bullets", "Match")
    database = schema_editor.connection.alias

    for evening in Evening.objects.using(database).all().iterator():
        matches = list(
            Match.objects.using(database)
            .filter(evening_id=evening.pk)
            .order_by("number")
        )
        if not matches:
            continue

        stored_round_sizes = Counter(match.round_number for match in matches)
        if max(stored_round_sizes.values()) <= evening.board_count:
            continue

        board_rounds = Counter()
        for match in matches:
            board_rounds[match.board] += 1
            match.round_number = board_rounds[match.board]
        Match.objects.using(database).bulk_update(matches, ["round_number"])


class Migration(migrations.Migration):
    dependencies = [
        ("bullets", "0007_alter_matchplayerstats_high_finishes"),
    ]

    operations = [
        migrations.RunPython(
            repair_legacy_block_rounds,
            migrations.RunPython.noop,
        ),
    ]