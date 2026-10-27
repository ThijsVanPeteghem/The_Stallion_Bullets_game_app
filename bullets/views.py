from collections import Counter

from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from .forms import EveningForm, MatchResultForm, PlayerEditForm, PlayerForm, SeasonForm
from .models import Attendance, Evening, Match, MatchPlayerStats, Player, Season
from .services import (
    build_standings,
    create_evening,
    evening_has_results,
    regenerate_evening_schedule,
    season_standings,
)


def home(request):
    seasons = Season.objects.all()
    recent_evenings = Evening.objects.select_related("season").order_by("-date")[:8]
    return render(
        request,
        "bullets/home.html",
        {"seasons": seasons, "recent_evenings": recent_evenings},
    )


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
    standings = build_standings(players, matches, attendances)
    match_counts = Counter(
        player_id
        for match in matches
        for player_id in (match.player1_id, match.player2_id)
        if player_id is not None
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
        "match_audit": [
            {
                "attendance": attendance,
                "matches": match_counts[attendance.player_id],
                "referees": referee_counts[attendance.player_id],
                "expected_matches": evening.match_count,
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
                stat.scores_177 = form.cleaned_data[f"{prefix}_177"]
                stat.scores_174 = form.cleaned_data[f"{prefix}_174"]
                stat.scores_171 = form.cleaned_data[f"{prefix}_171"]
                stat.least_darts = form.cleaned_data[f"{prefix}_least_darts"]
                stat.save()
        return redirect("evening_detail", evening_id=match.evening_id)
    return render(
        request,
        "bullets/match_edit.html",
        {"match": match, "form": form, "evening": match.evening},
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
                "scores_171": (stat.scores_171 or None) if stat else None,
                "scores_174": (stat.scores_174 or None) if stat else None,
                "scores_177": (stat.scores_177 or None) if stat else None,
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
    return render(
        request,
        "bullets/season_standings.html",
        {"season": season, "standings": season_standings(season)},
    )
