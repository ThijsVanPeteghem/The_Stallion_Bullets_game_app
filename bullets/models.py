from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Season(models.Model):
    name = models.CharField("seizoen", max_length=80, unique=True)

    class Meta:
        ordering = ["-name"]
        verbose_name = "seizoen"
        verbose_name_plural = "seizoenen"

    def __str__(self):
        return self.name


class Player(models.Model):
    name = models.CharField("naam", max_length=100, unique=True)
    active = models.BooleanField("actief", default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "speler"
        verbose_name_plural = "spelers"

    def __str__(self):
        return self.name


class Evening(models.Model):
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="evenings")
    date = models.DateField("datum")
    board_count = models.PositiveSmallIntegerField(
        "aantal dartsblokken", validators=[MinValueValidator(2), MaxValueValidator(30)]
    )
    match_count = models.PositiveSmallIntegerField(
        "aantal wedstrijden per speler",
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(20)],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date"]
        verbose_name = "competitieavond"
        verbose_name_plural = "competitieavonden"

    def __str__(self):
        return f"{self.season} - {self.date:%d-%m-%Y}"


class Attendance(models.Model):
    evening = models.ForeignKey(Evening, on_delete=models.CASCADE, related_name="attendances")
    player = models.ForeignKey(Player, on_delete=models.PROTECT, related_name="attendances")
    draw_order = models.PositiveSmallIntegerField("lotingsnummer")

    class Meta:
        ordering = ["draw_order"]
        constraints = [
            models.UniqueConstraint(fields=["evening", "player"], name="unique_evening_player"),
            models.UniqueConstraint(fields=["evening", "draw_order"], name="unique_evening_draw_order"),
        ]

    def __str__(self):
        return f"{self.draw_order}. {self.player}"


class Match(models.Model):
    evening = models.ForeignKey(Evening, on_delete=models.CASCADE, related_name="matches")
    number = models.PositiveSmallIntegerField("wedstrijdnummer")
    round_number = models.PositiveSmallIntegerField("speelronde")
    board = models.PositiveSmallIntegerField("dartsblok")
    player1 = models.ForeignKey(
        Player, on_delete=models.PROTECT, related_name="matches_as_player1"
    )
    player2 = models.ForeignKey(
        Player,
        on_delete=models.PROTECT,
        related_name="matches_as_player2",
        null=True,
        blank=True,
    )
    referee = models.ForeignKey(
        Player,
        on_delete=models.PROTECT,
        related_name="refereed_matches",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["evening", "number"], name="unique_evening_match_number")
        ]

    def __str__(self):
        opponent = str(self.player2) if self.player2_id else "Stroman"
        return f"Wedstrijd {self.number}: {self.player1} - {opponent}"

    @property
    def is_phantom_match(self):
        return self.player2_id is None

    @property
    def is_complete(self):
        stats = list(self.stats.all())
        expected = 1 if self.is_phantom_match else 2
        return len(stats) == expected and all(stat.legs_won is not None for stat in stats)

    def stats_for(self, player):
        return next((stat for stat in self.stats.all() if stat.player_id == player.id), None)


class MatchPlayerStats(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="stats")
    player = models.ForeignKey(Player, on_delete=models.PROTECT, related_name="match_stats")
    is_stroman = models.BooleanField("speelt als stroman", default=False)
    legs_won = models.PositiveSmallIntegerField(
        "legs gewonnen",
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(3)],
    )
    high_finishes = models.CharField(
        "finishes",
        max_length=200,
        blank=True,
        help_text="Vul finishwaarden van 2 t/m 170 in; alleen 100+ telt mee voor punten.",
    )
    scores_180 = models.PositiveSmallIntegerField("180 worpen", default=0)
    scores_177 = models.PositiveSmallIntegerField("177 worpen", default=0)
    scores_174 = models.PositiveSmallIntegerField("174 worpen", default=0)
    scores_171 = models.PositiveSmallIntegerField("171 worpen", default=0)
    least_darts = models.CharField(
        "pijlen per leg",
        max_length=20,
        blank=True,
        default="",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["match", "player"], name="unique_match_player_stats")
        ]

    def finish_values(self):
        if not self.high_finishes.strip():
            return []
        try:
            values = [int(value.strip()) for value in self.high_finishes.split(",")]
        except ValueError:
            return []
        return [value for value in values if 2 <= value <= 170]

    def least_darts_values(self):
        if not self.least_darts or not self.least_darts.strip():
            return []
        try:
            values = [int(value.strip()) for value in self.least_darts.split(",")]
        except ValueError:
            return []
        return [value for value in values if 1 <= value <= 99]

    @property
    def bonus_points(self):
        finish_points = sum(
            1 if 100 <= value <= 160 else 2 if value in {161, 164, 167, 170} else 0
            for value in self.finish_values()
        )
        return self.scores_180 + self.scores_171 + finish_points

    @property
    def points(self):
        leg_points = (
            0
            if self.is_stroman or self.match.is_phantom_match
            else (self.legs_won or 0)
        )
        return leg_points + self.bonus_points

    @property
    def highest_throw(self):
        return next(
            (score for score, count in ((180, self.scores_180), (177, self.scores_177),
                                        (174, self.scores_174), (171, self.scores_171)) if count),
            None,
        )
