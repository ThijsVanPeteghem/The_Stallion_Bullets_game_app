from collections import Counter

from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from .forms import EveningForm, MatchResultForm, PlayerEditForm, PlayerForm, SeasonForm
from .models import Attendance, Evening, Match, MatchPlayerStats, Player, Season
from .services import (
    build_standings,
    create_evening,
    evening_has_results,
    regenerate_evening_schedule,
    season_standings,
    sort_standings_for_ranking,
)
from .schedule import expected_match_count


def home(request):
    seasons = Season.objects.all()
    recent_evenings = Evening.objects.select_related("season").order_by("-date")[:8]
    return render(
        request,
        "bullets/home.html",
        {"seasons": seasons, "recent_evenings": recent_evenings},
    )


def rules(request):
    return render(request, "bullets/rules.html")


def players(request):
    form = PlayerForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("players")
    return render(
        request,
        "bullets/players.html",
        {"players": Player.objects.all(), "form": form},
    )


def player_detail(request, player_id):
    player = get_object_or_404(Player, pk=player_id)
    matches = list(
        Match.objects.filter(Q(player1=player) | Q(player2=player))
        .select_related("evening", "evening__season", "player1", "player2", "referee")
        .prefetch_related("stats")
        .order_by("-evening__date", "-number")
    )
    opponent_counts = Counter()
    totals = Counter()
    high_finish_values = []
    least_darts_values = []
    played_count = 0
    match_rows = []
    for match in matches:
        stats = list(match.stats.all())
        player_stats = next((stat for stat in stats if stat.player_id == player.id), None)
        opponent = match.player2 if match.player1_id == player.id else match.player1
        complete = match.is_complete
        opponent_stats = next(
            (stat for stat in stats if opponent and stat.player_id == opponent.id), None
        )
        if complete:
            played_count += 1
            if opponent:
                opponent_counts[opponent] += 1
        if complete and player_stats:
            finishes = player_stats.finish_values()
            totals["high_finishes"] += len(finishes)
            high_finish_values.extend(finishes)
            darts_values = player_stats.least_darts_values()
            totals["least_darts"] += len(darts_values)
            least_darts_values.extend(darts_values)
            totals["scores_171"] += player_stats.scores_171
            totals["scores_180"] += player_stats.scores_180
        match_rows.append(
            {
                "match": match,
                "opponent": opponent,
                "stats": player_stats,
                "is_stroman": bool(player_stats and player_stats.is_stroman),
                "opponent_stats": opponent_stats,
                "high_finishes": (
                    player_stats.finish_values()
                    if complete and player_stats
                    else []
                ),
            }
        )

    return render(
        request,
        "bullets/player_detail.html",
        {
            "player": player,
            "matches": match_rows,
            "opponents": sorted(
                opponent_counts.items(),
                key=lambda item: (-item[1], item[0].name.casefold()),
            ),
            "played_count": played_count,
            "refereed_count": Match.objects.filter(referee=player).count(),
            "totals": totals,
            "high_finish_values": high_finish_values,
            "least_darts_values": least_darts_values,
        },
    )


def edit_player(request, player_id):
    player = get_object_or_404(Player, pk=player_id)
    form = PlayerEditForm(request.POST or None, instance=player)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("players")
    return render(request, "bullets/player_edit.html", {"form": form, "player": player})


def seasons(request):
    form = SeasonForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        season = form.save()
        return redirect("season_detail", season_id=season.id)
    return render(request, "bullets/seasons.html", {"form": form, "seasons": Season.objects.all()})


def season_detail(request, season_id):
    season = get_object_or_404(Season, pk=season_id)
    return render(
        request,
        "bullets/season_detail.html",
        {
            "season": season,
            "evenings": season.evenings.all(),
            "standings": season_standings(season),
        },
    )


def new_evening(request):
    form = EveningForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        evening = create_evening(
            season=form.cleaned_data["season"],
            date=form.cleaned_data["date"],
            board_count=form.cleaned_data["board_count"],
            match_count=form.cleaned_data["match_count"],
            players=form.cleaned_data["ordered_players"],
            stroman_player=form.cleaned_data.get("stroman_player"),
        )
        return redirect("evening_detail", evening_id=evening.id)
    return render(request, "bullets/new_evening.html", {"form": form})


def _evening_context(evening):
    attendances = list(
        evening.attendances.select_related("player").order_by("draw_order")
    )
    players = [attendance.player for attendance in attendances]
    matches = list(
        evening.matches.select_related("player1", "player2", "referee")
        .prefetch_related("stats")
    )
    for match in matches:
        stroman_stats = [stat for stat in match.stats.all() if stat.is_stroman]
        match.stroman_player_id = stroman_stats[0].player_id if stroman_stats else None
    standings = build_standings(players, matches, attendances)
    match_counts = Counter(
        player_id
        for match in matches
        for player_id in (match.player1_id, match.player2_id)
        if player_id is not None
    )
    max_points = max((row["points"] for row in standings), default=0)
    for row in standings:
        scheduled_count = match_counts[row["player"].id]
        row["matches_scheduled"] = scheduled_count
        row["points_progress"] = (
            round(row["points"] * 100 / max_points)
            if max_points > 0
            else 0
        )
        row["matches_progress"] = (
            round(row["matches_played"] * 100 / scheduled_count)
            if scheduled_count > 0
            else 0
        )
    stroman_match_counts = Counter(
        stat.player_id
        for match in matches
        for stat in match.stats.all()
        if stat.is_stroman
    )
    expected_stroman_matches = int(
        len(players) % 2 == 1 and evening.match_count % 2 == 1
    )
    round_participants = {}
    rounds_valid = True
    for match in matches:
        participants = {
            player_id
            for player_id in (match.player1_id, match.player2_id)
            if player_id is not None
        }
        round_players = round_participants.setdefault(match.round_number, set())
        if round_players & participants:
            rounds_valid = False
        round_players.update(participants)
    expected_total_matches = expected_match_count(
        len(players),
        evening.match_count,
    )
    stroman_match_total = sum(stroman_match_counts.values())
    stroman_match_is_last = (
        not stroman_match_total
        or any(
            match.number == matches[-1].number
            and any(stat.is_stroman for stat in match.stats.all())
            for match in matches
        )
    )
    referee_counts = Counter(
        match.referee_id for match in matches if match.referee_id is not None
    )
    return {
        "evening": evening,
        "attendances": attendances,
        "matches": matches,
        "standings": standings,
        "complete_count": sum(match.is_complete for match in matches),
        "schedule_audit": {
            "expected_matches": expected_total_matches,
            "actual_matches": len(matches),
            "expected_stroman_matches": expected_stroman_matches,
            "actual_stroman_matches": stroman_match_total,
            "valid": (
                len(matches) == expected_total_matches
                and stroman_match_total == expected_stroman_matches
                and stroman_match_is_last
                and all(
                    match_counts[attendance.player_id]
                    == (
                        evening.match_count + 1
                        if stroman_match_counts[attendance.player_id]
                        and match_counts[attendance.player_id] > evening.match_count
                        else evening.match_count
                    )
                    for attendance in attendances
                )
                and rounds_valid
            ),
        },
        "match_audit": [
            {
                "attendance": attendance,
                "matches": match_counts[attendance.player_id],
                "stroman_matches": stroman_match_counts[attendance.player_id],
                "referees": referee_counts[attendance.player_id],
                "expected_matches": (
                    evening.match_count + 1
                    if stroman_match_counts[attendance.player_id]
                    and match_counts[attendance.player_id] > evening.match_count
                    else evening.match_count
                ),
            }
            for attendance in attendances
        ],
    }


def evening_detail(request, evening_id):
    evening = get_object_or_404(Evening.objects.select_related("season"), pk=evening_id)
    context = _evening_context(evening)
    context["can_regenerate_schedule"] = not evening_has_results(evening)
    return render(request, "bullets/evening_detail.html", context)


def evening_standings_view(request, evening_id):
    evening = get_object_or_404(Evening.objects.select_related("season"), pk=evening_id)
    context = _evening_context(evening)
    return render(request, "bullets/evening_standings.html", context)


def regenerate_schedule_view(request, evening_id):
    evening = get_object_or_404(Evening.objects.select_related("season"), pk=evening_id)
    if request.method == "POST":
        try:
            regenerate_evening_schedule(evening)
        except ValueError as error:
            return render(
                request,
                "bullets/evening_regenerate.html",
                {"evening": evening, "error": str(error)},
                status=400,
            )
        return redirect("evening_detail", evening_id=evening.id)
    return render(
        request,
        "bullets/evening_regenerate.html",
        {"evening": evening, "error": ""},
    )

def delete_evening(request, evening_id):
    evening = get_object_or_404(Evening.objects.select_related("season"), pk=evening_id)
    if request.method == "POST":
        season_id = evening.season_id
        evening.delete()
        return redirect("season_detail", season_id=season_id)
    return render(request, "bullets/evening_confirm_delete.html", {"evening": evening})


def edit_match(request, match_id):
    match = get_object_or_404(
        Match.objects.select_related("evening", "evening__season", "player1", "player2", "referee")
        .prefetch_related("stats"),
        pk=match_id,
    )
    form = MatchResultForm(request.POST or None, match=match)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            prefixes = [("p1", match.player1)]
            if match.player2_id:
                prefixes.append(("p2", match.player2))
            for prefix, player in prefixes:
                stat, _ = MatchPlayerStats.objects.get_or_create(match=match, player=player)
                stat.legs_won = form.cleaned_data[f"{prefix}_legs"]
                stat.high_finishes = form.cleaned_data[f"{prefix}_high_finishes"]
                stat.scores_180 = form.cleaned_data[f"{prefix}_180"]
                stat.scores_171 = form.cleaned_data[f"{prefix}_171"]
                stat.least_darts = form.cleaned_data[f"{prefix}_least_darts"]
                stat.save()
        return redirect("evening_detail", evening_id=match.evening_id)
    return render(
        request,
        "bullets/match_edit.html",
        {
            "match": match,
            "form": form,
            "evening": match.evening,
            "stroman_player_ids": {
                stat.player_id for stat in match.stats.all() if stat.is_stroman
            },
        },
    )


def print_evening(request, evening_id):
    evening = get_object_or_404(Evening.objects.select_related("season"), pk=evening_id)
    matches = list(
        evening.matches.select_related("player1", "player2", "referee").order_by("number")
        .prefetch_related("stats")
    )
    print_matches = []
    for match in matches:
        stats_by_player = {stat.player_id: stat for stat in match.stats.all()}
        players = [match.player1, match.player2]
        player_rows = []
        for player in players:
            stat = stats_by_player.get(player.id) if player else None
            player_rows.append({
                "player": player if player else "Stroman",
                "legs_won": stat.legs_won if stat else None,
                "is_stroman": bool(stat and stat.is_stroman),
                "scores_171": (stat.scores_171 or None) if stat else None,
                "scores_180": (stat.scores_180 or None) if stat else None,
                "high_finishes": (len(stat.finish_values()) or None) if stat else None,
                "least_darts": stat.least_darts if stat else "",
            })
        print_matches.append({"match": match, "player_rows": player_rows})
    return render(
        request,
        "bullets/print_evening.html",
        {"evening": evening, "matches": print_matches},
    )


def season_standings_view(request, season_id):
    season = get_object_or_404(Season, pk=season_id)
    evenings = list(season.evenings.order_by("date", "pk"))
    ranking_tabs = [
        {"key": "points", "label": "Punten"},
        {"key": "scores_180", "label": "180 worpen"},
        {"key": "scores_171", "label": "171 worpen"},
        {"key": "highest_finish", "label": "Hoogste finish"},
        {"key": "least_darts", "label": "Minste pijlen"},
    ]
    selected_ranking = request.GET.get("ranking", "points")
    if selected_ranking not in {tab["key"] for tab in ranking_tabs}:
        raise Http404("Dit klassement bestaat niet.")
    evening_id = request.GET.get("evening")
    selected_index = len(evenings) - 1
    if evening_id:
        selected_index = next(
            (index for index, evening in enumerate(evenings) if str(evening.pk) == evening_id),
            None,
        )
        if selected_index is None:
            raise Http404("Deze speeldag bestaat niet in dit seizoen.")
    selected_evening = evenings[selected_index] if evenings else None
    standings = season_standings(season, selected_evening)
    if selected_ranking != "points":
        standings = sort_standings_for_ranking(standings, selected_ranking)
    for tab in ranking_tabs:
        tab["active"] = tab["key"] == selected_ranking
    ranking_labels = {
        tab["key"]: tab["label"] for tab in ranking_tabs
    }
    return render(
        request,
        "bullets/season_standings.html",
        {
            "season": season,
            "standings": standings,
            "evenings": evenings,
            "selected_evening": selected_evening,
            "selected_number": selected_index + 1,
            "previous_evening": evenings[selected_index - 1] if selected_index > 0 else None,
            "next_evening": (
                evenings[selected_index + 1] if selected_index + 1 < len(evenings) else None
            ),
            "ranking_tabs": ranking_tabs,
            "selected_ranking": selected_ranking,
            "ranking_label": ranking_labels[selected_ranking],
            "show_position_change": selected_ranking == "points",
        },
    )
