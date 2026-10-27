from django import forms
from django.core.exceptions import ValidationError
import json

from .models import Player, Season


class PlayerForm(forms.ModelForm):
    class Meta:
        model = Player
        fields = ["name"]
        labels = {"name": "Naam"}

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        duplicates = Player.objects.filter(name__iexact=name)
        if self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise ValidationError("Er bestaat al een speler met deze naam.")
        return name


class PlayerEditForm(PlayerForm):
    class Meta(PlayerForm.Meta):
        fields = ["name", "active"]
        labels = {"name": "Naam", "active": "Actief"}


class SeasonForm(forms.ModelForm):
    class Meta:
        model = Season
        fields = ["name"]


class EveningForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["players"] = forms.ModelMultipleChoiceField(
            queryset=Player.objects.filter(active=True),
            label="Aanwezige spelers",
            widget=forms.CheckboxSelectMultiple,
            required=True,
        )
        self.fields["draw_order"] = forms.CharField(widget=forms.HiddenInput)

    season = forms.ModelChoiceField(queryset=Season.objects.all(), label="Seizoen")
    date = forms.DateField(
        label="Datum",
        input_formats=["%d/%m/%Y"],
        widget=forms.DateInput(
            format="%d/%m/%Y",
            attrs={"type": "text", "placeholder": "dd/MM/yyyy"},
        ),
    )
    board_count = forms.IntegerField(
        label="Aantal dartsblokken",
        min_value=2,
        max_value=30,
        initial=4,
    )
    match_count = forms.IntegerField(
        label="Aantal wedstrijden per speler",
        min_value=1,
        max_value=20,
        initial=5,
    )

    def clean(self):
        cleaned_data = super().clean()
        selected_players = cleaned_data.get("players")
        if selected_players is None:
            return cleaned_data

        players = list(selected_players)
        if not 4 <= len(players) <= 128:
            self.add_error("players", "Selecteer minimaal 4 en maximaal 128 aanwezige spelers.")
            return cleaned_data

        try:
            order = json.loads(cleaned_data.get("draw_order", ""))
            order = [int(player_id) for player_id in order]
        except (TypeError, ValueError):
            self.add_error("draw_order", "Selecteer de spelers en controleer hun lotingsvolgorde.")
            return cleaned_data

        players_by_id = {player.id: player for player in players}
        if len(order) != len(set(order)) or set(order) != set(players_by_id):
            self.add_error("draw_order", "De lotingsvolgorde moet alle geselecteerde spelers bevatten.")
            return cleaned_data
        cleaned_data["ordered_players"] = [players_by_id[player_id] for player_id in order]
        return cleaned_data


class MatchResultForm(forms.Form):
    def __init__(self, *args, match, **kwargs):
        super().__init__(*args, **kwargs)
        self.match = match
        players = [("p1", match.player1)]
        if match.player2_id:
            players.append(("p2", match.player2))
        existing = {stat.player_id: stat for stat in match.stats.all()}
        for prefix, player in players:
            stat = existing.get(player.id)
            values = {
                "legs": (stat.legs_won if stat else None),
                "high_finishes": (stat.high_finishes if stat else ""),
                "180": (stat.scores_180 if stat else 0),
                "177": (stat.scores_177 if stat else 0),
                "174": (stat.scores_174 if stat else 0),
                "171": (stat.scores_171 if stat else 0),
                "least_darts": (stat.least_darts if stat else ""),
            }
            self.fields[f"{prefix}_legs"] = forms.IntegerField(
                label=f"{player} - legs gewonnen", min_value=0, max_value=3,
                initial=values["legs"],
            )
            self.fields[f"{prefix}_high_finishes"] = forms.CharField(
                label=f"{player} - high finishes",
                required=False,
                initial=values["high_finishes"],
                help_text="100+ finishes, komma-gescheiden",
            )
            for score in (180, 177, 174, 171):
                self.fields[f"{prefix}_{score}"] = forms.IntegerField(
                    label=f"{player} - {score} worpen",
                    min_value=0,
                    initial=values[str(score)],
                )
            self.fields[f"{prefix}_least_darts"] = forms.CharField(
                label=f"{player} - minste pijlen",
                required=False,
                initial=values["least_darts"],
                help_text="Pijlen per leg (1-15), komma-gescheiden; bijvoorbeeld 13, 15.",
            )

    def clean(self):
        cleaned_data = super().clean()
        if self.match.player2_id and all(
            f"{prefix}_legs" in cleaned_data for prefix in ("p1", "p2")
        ):
            if cleaned_data["p1_legs"] + cleaned_data["p2_legs"] != 3:
                raise ValidationError("De legs moeten samen exact 3 zijn.")
        for prefix in ("p1", "p2"):
            field = f"{prefix}_high_finishes"
            if field in cleaned_data:
                raw = cleaned_data[field].strip()
                if not raw:
                    cleaned_data[field] = ""
                else:
                    try:
                        finishes = [int(value.strip()) for value in raw.split(",")]
                    except ValueError:
                        self.add_error(field, "Vul finishwaarden in, gescheiden door komma's.")
                    else:
                        if any(value < 100 or value > 170 for value in finishes):
                            self.add_error(field, "Een high finish moet tussen 100 en 170 liggen.")
                        else:
                            cleaned_data[field] = ", ".join(
                                str(value) for value in finishes
                            )
            field = f"{prefix}_least_darts"
            if field not in cleaned_data:
                continue
            raw = cleaned_data[field].strip()
            if not raw:
                cleaned_data[field] = ""
                continue
            try:
                darts_per_leg = [int(value.strip()) for value in raw.split(",")]
            except ValueError:
                self.add_error(field, "Vul het aantal pijlen per leg in, gescheiden door komma's.")
                continue
            if len(darts_per_leg) > 3:
                self.add_error(field, "Vul maximaal drie legs in.")
            elif any(value < 1 or value > 15 for value in darts_per_leg):
                self.add_error(field, "Een leg met bonus moet tussen 1 en 15 pijlen bevatten.")
            else:
                cleaned_data[field] = ", ".join(
                    str(value) for value in darts_per_leg
                )
        return cleaned_data
