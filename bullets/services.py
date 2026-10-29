from django.db import transaction

from .models import Attendance, Evening, Match, MatchPlayerStats, Player
from .schedule import StromanSelectionError, generate_schedule


def _create_matches(evening, players, stroman_player=None):
    stroman_index = (
        next(
            (
                index
                for index, player in enumerate(players)
                if stroman_player is not None and player.id == stroman_player.id
            ),
            None,
        )
        if stroman_player is not None
        else None
    )
    if stroman_player is not None and stroman_index is None:
        raise ValueError("De gekozen stroman moet bij deze competitieavond aanwezig zijn.")
    scheduled = generate_schedule(
        len(players),
        evening.board_count,
        evening.match_count,
        stroman_player=stroman_index,
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
        MatchPlayerStats.objects.create(
            match=match,
            player=player1,
            is_stroman=item.get("stroman_player") == item["player1"],
        )
        if player2:
            MatchPlayerStats.objects.create(
                match=match,
                player=player2,
                is_stroman=item.get("stroman_player") == item["player2"],
            )


@transaction.atomic
def create_evening(
    *,
    season,
    date,
    board_count,
    players,
    match_count=5,
    stroman_player=None,
):
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
    _create_matches(evening, players, stroman_player)
    return evening


@transaction.atomic
def regenerate_evening_schedule(evening):
    if evening_has_results(evening):
        raise ValueError("Een schema met ingevoerde uitslagen of statistieken kan niet opnieuw worden opgemaakt.")

    players = list(
        Player.objects.filter(attendances__evening=evening)
        .order_by("attendances__draw_order")
    )
    stroman_stats = MatchPlayerStats.objects.filter(
        match__evening=evening,
        is_stroman=True,
    ).select_related("player").first()
    stroman_match = evening.matches.filter(player2__isnull=True).first()
    stroman_player = (
        stroman_stats.player
        if stroman_stats
        else stroman_match.player1 if stroman_match else None
    )
    evening.matches.all().delete()
    _create_matches(evening, players, stroman_player)


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
            "scores_171": 0,
            "scores_180": 0,
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
            if not match.is_phantom_match and not stat.is_stroman:
                row["matches_played"] += 1
                row["legs_for"] += stat.legs_won or 0
            row["high_finishes"] += len(stat.finish_values())
            finish_values = stat.finish_values()
            if finish_values:
                row["highest_finish"] = max(
                    filter(None, [row["highest_finish"], max(finish_values)])
                )
            row["scores_171"] += stat.scores_171
            row["scores_180"] += stat.scores_180
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
                for stat, opponent_stat in ((first, second), (second, first)):
                    if stat.is_stroman:
                        continue
                    rows[stat.player_id]["legs_against"] += opponent_stat.legs_won or 0
                    if stat.legs_won > opponent_stat.legs_won:
                        rows[stat.player_id]["wins"] += 1
                    else:
                        rows[stat.player_id]["losses"] += 1
    for row in rows.values():
        row["legs_balance"] = row["legs_for"] - row["legs_against"]
    return list(rows.values())


def season_standings(season, through_evening=None):
    evenings = season.evenings.order_by("date", "pk")
    if through_evening is not None:
        evening_ids = []
        for evening in evenings:
            evening_ids.append(evening.pk)
            if evening.pk == through_evening.pk:
                break
        else:
            raise ValueError("De gekozen speeldag hoort niet bij dit seizoen.")
    else:
        evening_ids = list(evenings.values_list("pk", flat=True))

    attendances = list(
        Attendance.objects.filter(evening_id__in=evening_ids)
        .select_related("player", "evening")
        .order_by("evening__date", "evening_id", "draw_order")
    )
    matches = list(
        Match.objects.filter(evening_id__in=evening_ids)
        .select_related("player1", "player2", "referee")
        .prefetch_related("stats")
    )
    rows = _rank_season_standings(attendances, matches)
    previous_rows = (
        _rank_season_standings(
            [record for record in attendances if record.evening_id != evening_ids[-1]],
            [match for match in matches if match.evening_id != evening_ids[-1]],
        )
        if len(evening_ids) > 1
        else []
    )
    previous_positions = {
        row["player"].pk: position
        for position, row in enumerate(previous_rows, start=1)
    }
    for position, row in enumerate(rows, start=1):
        previous_position = previous_positions.get(row["player"].pk)
        row["position_change"] = (
            previous_position - position if previous_position is not None else None
        )
    return rows


def sort_standings_for_ranking(rows, ranking):
    ranking_keys = {
        "scores_180": lambda row: (
            row["scores_180"] == 0,
            -row["scores_180"],
        ),
        "scores_171": lambda row: (
            row["scores_171"] == 0,
            -row["scores_171"],
        ),
        "highest_finish": lambda row: (
            row["highest_finish"] is None,
            -(row["highest_finish"] or 0),
        ),
        "least_darts": lambda row: (
            row["least_darts"] is None,
            row["least_darts"] or 0,
        ),
    }
    if ranking not in ranking_keys:
        raise ValueError(f"Onbekend extra klassement: {ranking}")
    return sorted(rows, key=ranking_keys[ranking])


def _rank_season_standings(attendances, matches):
    players = list({record.player_id: record.player for record in attendances}.values())
    rows = build_standings(players, matches)
    return sorted(
        rows,
        key=lambda row: (
            -row["points"],
            row["matches_played"],
            -row["legs_balance"],
            -(row["highest_finish"] or 0),
            -row["scores_180"],
            row["player"].name.casefold(),
        ),
    )
