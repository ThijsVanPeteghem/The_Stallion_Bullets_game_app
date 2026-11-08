from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bullets", "0010_match_is_relevant"),
    ]

    operations = [
        migrations.AddField(
            model_name="match",
            name="is_called",
            field=models.BooleanField(default=False, verbose_name="afgeroepen"),
        ),
    ]
