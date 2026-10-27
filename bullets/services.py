from django.db import transaction

from .models import Attendance, Evening, Match, MatchPlayerStats, Player
from .schedule import generate_schedule


def _create_matches(evening, players):
    scheduled = generate_schedule(
        len(players),
        evening.board_count,
        evening.match_count,
    )
    for item in scheduled:
        player1 = players[item["player1"]]
        player2 = players[item["player2"]] if isinstance(item["player2"], int) else None
        referee = players[item["referee"]] if isinstance(item["referee"], int) else None
        match = Match.objects.create(
            evening=evening,
            number=item["number"],
            round_number=item["round"],
            board=item["board"],
            player1=player1,
            player2=player2,
            referee=referee,
        )
        MatchPlayerStats.objects.create(match=match, player=player1)
        if player2:
            MatchPlayerStats.objects.create(match=match, player=player2)


@transaction.atomic
def create_evening(*, season, date, board_count, players, match_count=5):
    evening = Evening.objects.create(
        season=season,
        date=date,
        board_count=board_count,
        match_count=match_count,
    )
    for draw_order, player in enumerate(players, start=1):
        Attendance.objects.create(
            evening=evening, player=player, draw_order=draw_order
        )
    _create_matches(evening, players)
    return evening


@transaction.atomic
def regenerate_evening_schedule(evening):
    if evening_has_results(evening):
        raise ValueError("Een schema met ingevoerde uitslagen of statistieken kan niet opnieuw worden opgemaakt.")

    players = list(
        Player.objects.filter(attendances__evening=evening)
        .order_by("attendances__draw_order")
    )
    evening.matches.all().delete()
    _create_matches(evening, players)


def evening_has_results(evening):
    stats = MatchPlayerStats.objects.filter(match__evening=evening)
    return (
        stats.filter(legs_won__isnull=False).exists()
        or stats.exclude(high_finishes="").exists()
        or stats.exclude(scores_180=0, scores_177=0, scores_174=0, scores_171=0).exists()
        or stats.exclude(least_darts="").exists()
    )


def build_standings(players, matches, attendance=None):
    rows = {
        player.id: {
            "player": player,
            "points": 0,
            "high_finishes": 0,
            "highest_finish": None,
            "highest_throw": None,
            "least_darts": None,
            "matches_played": 0,
            "refereed": 0,
            "legs_for": 0,
            "legs_against": 0,
            "wins": 0,
            "losses": 0,
        }
        for player in players
    }
    if attendance:
        for record in attendance:
            rows[record.player_id]["draw_order"] = record.draw_order

    for match in matches:
        if match.referee_id in rows:
            rows[match.referee_id]["refereed"] += 1
        if not match.is_complete:
            continue
        stats = list(match.stats.all())
        for stat in stats:
            row = rows.get(stat.player_id)
            if row is None:
                continue
            row["points"] += stat.points
            row["matches_played"] += 1
            row["legs_for"] += stat.legs_won or 0
            row["high_finishes"] += len(stat.finish_values())
            finish_values = stat.finish_values()
            if finish_values:
                row["highest_finish"] = max(
                    filter(None, [row["highest_finish"], max(finish_values)])
                )
            if stat.highest_throw:
                row["highest_throw"] = max(
                    filter(None, [row["highest_throw"], stat.highest_throw])
                )
            darts_values = stat.least_darts_values()
            if darts_values:
                row["least_darts"] = min(
                    filter(None, [row["least_darts"], min(darts_values)])
                )
        if match.player2_id:
            stat_by_player = {stat.player_id: stat for stat in stats}
            first = stat_by_player.get(match.player1_id)
            second = stat_by_player.get(match.player2_id)
            if first and second:
                rows[match.player1_id]["legs_against"] += second.legs_won or 0
                rows[match.player2_id]["legs_against"] += first.legs_won or 0
                if first.legs_won > second.legs_won:
                    rows[match.player1_id]["wins"] += 1
                    rows[match.player2_id]["losses"] += 1
                else:
                    rows[match.player2_id]["wins"] += 1
                    rows[match.player1_id]["losses"] += 1
        elif stats:
            stat = stats[0]
            opponent_legs = 3 - (stat.legs_won or 0)
            rows[stat.player_id]["legs_against"] += opponent_legs
            if (stat.legs_won or 0) > opponent_legs:
                rows[stat.player_id]["wins"] += 1
            else:
                rows[stat.player_id]["losses"] += 1
    return list(rows.values())


def season_standings(season):
    attendances = list(
        Attendance.objects.filter(evening__season=season)
        .select_related("player", "evening")
        .order_by("evening__date", "draw_order")
    )
    players = list({record.player_id: record.player for record in attendances}.values())
    matches = list(
        Match.objects.filter(evening__season=season)
        .select_related("player1", "player2", "referee")
        .prefetch_related("stats")
    )
    rows = build_standings(players, matches)
    return sorted(
        rows,
        key=lambda row: (
            -row["points"], -row["legs_for"], row["legs_against"], row["player"].name.casefold()
        ),
    )
