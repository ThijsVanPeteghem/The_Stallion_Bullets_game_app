from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("bullets", "0009_match_player_rounds_json")]

    operations = [
        migrations.AddField(
            model_name="match",
            name="is_relevant",
            field=models.BooleanField(default=True, verbose_name="telt mee"),
        ),
    ]