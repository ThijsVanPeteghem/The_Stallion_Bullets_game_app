import json
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .legacy_import import parse_legacy_file
from .models import Attendance, Evening, Match, MatchPlayerStats, Player, Season
from .schedule import expected_match_count, generate_schedule
from .services import (
    build_standings,
    create_evening,
    season_standings,
    sort_standings_for_ranking,
)
from .snapshots import create_database_snapshot


class DatabaseSnapshotTests(SimpleTestCase):
    def test_snapshot_is_consistent_timestamped_and_never_overwrites(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "competition.sqlite3"
            snapshots = root / "snapshots"
            with closing(sqlite3.connect(source)) as connection:
                connection.execute("CREATE TABLE sample (value TEXT NOT NULL)")
                connection.execute("INSERT INTO sample VALUES ('snapshot data')")
                connection.commit()

            timestamp = datetime(2026, 10, 28, 0, 7, 0)
            first = create_database_snapshot(source, snapshots, timestamp)
            second = create_database_snapshot(source, snapshots, timestamp)

            self.assertEqual(first.name, "competition_20261028_000700.sqlite3")
            self.assertEqual(second.name, "competition_20261028_000700_02.sqlite3")
            for snapshot in (first, second):
                with closing(sqlite3.connect(snapshot)) as connection:
                    self.assertEqual(
                        connection.execute("PRAGMA integrity_check").fetchone(),
                        ("ok",),
                    )
                    self.assertEqual(
                        connection.execute("SELECT value FROM sample").fetchone(),
                        ("snapshot data",),
                    )
            self.assertEqual(list(snapshots.glob("*.tmp.sqlite3")), [])

    def test_snapshot_rejects_missing_database_file(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            with self.assertRaises(FileNotFoundError):
                create_database_snapshot(root / "missing.sqlite3", root / "snapshots")


class ScheduleTests(SimpleTestCase):
    def test_expected_total_covers_every_supported_roster_and_game_count(self):
        for player_count in range(4, 129):
            for match_count in range(1, 21):
                with self.subTest(players=player_count, matches=match_count):
                    self.assertEqual(
                        expected_match_count(player_count, match_count),
                        (player_count * match_count + 1) // 2,
                    )

class LegacyImportTests(TestCase):
    source_dir = settings.BASE_DIR / "old_format_data"

    def test_legacy_files_parse_with_results_and_stroman_designation(self):
        parsed = [
            parse_legacy_file(self.source_dir / "speeldag1__04-09-2026.txt"),
            parse_legacy_file(self.source_dir / "speeldag2__02-10-2026.txt"),
        ]

        self.assertEqual([len(item["matches"]) for item in parsed], [63, 63])
        self.assertEqual([item["match_count"] for item in parsed], [5, 5])
        self.assertEqual([item["stroman"] for item in parsed], ["Mario Loman", "Tim De Neve"])
        self.assertEqual([len(item["players"]) for item in parsed], [25, 25])
        self.assertEqual(parsed[0]["matches"][-1]["players"][1]["scores_180"], 1)
        self.assertEqual(parsed[0]["matches"][9]["players"][0]["high_finishes"], "74")
        self.assertEqual(parsed[1]["matches"][6]["players"][0]["least_darts"], "15")

    def test_legacy_import_creates_complete_season_history_without_duplicate_imports(self):
        call_command(
            "import_legacy_data",
            "--source",
            str(self.source_dir),
            stdout=None,
        )

        season = Season.objects.get(name="2026-2027")
        evenings = list(season.evenings.order_by("date"))
        self.assertEqual([evening.date.isoformat() for evening in evenings], [
            "2026-09-04",
            "2026-10-02",
        ])
        self.assertEqual(Player.objects.count(), 31)
        for evening in evenings:
            self.assertEqual(evening.attendances.count(), 25)
            self.assertEqual(evening.match_count, 5)
            self.assertEqual(evening.matches.count(), 63)
            self.assertEqual(evening.matches.filter(referee__isnull=False).count(), 63)
            self.assertEqual(evening.matches.first().stats.count(), 2)
            self.assertEqual(
                evening.matches.filter(stats__is_stroman=True).count(),
                1,
            )
            stroman_stat = MatchPlayerStats.objects.get(
                match__evening=evening,
                is_stroman=True,
            )
            self.assertEqual(stroman_stat.match.number, 63)
            self.assertEqual(stroman_stat.legs_won, 3 if evening.date.month == 9 else 0)
            self.assertEqual(stroman_stat.points, (
                stroman_stat.scores_180
                + stroman_stat.scores_171
                + sum(
                    1 if 100 <= value <= 160 else 2 if value in {161, 164, 167, 170} else 0
                    for value in stroman_stat.finish_values()
                )
            ))
            appearances = Counter(
                player_id
                for match in evening.matches.all()
                for player_id in (match.player1_id, match.player2_id)
            )
            self.assertEqual(sorted(appearances.values()), [5] * 24 + [6])
            audit_response = self.client.get(
                reverse("evening_detail", args=[evening.id])
            )
            self.assertTrue(audit_response.context["schedule_audit"]["valid"])

        with self.assertRaises(CommandError):
            call_command(
                "import_legacy_data",
                "--source",
                str(self.source_dir),
            )
        self.assertEqual(season.evenings.count(), 2)

    def test_five_game_schedule_totals_and_final_stroman_match(self):
        expected_totals = {
            20: 50,
            21: 53,
            22: 55,
            23: 58,
            24: 60,
            25: 63,
            26: 65,
            27: 68,
            28: 70,
            29: 73,
            30: 75,
        }
        for player_count, expected_match_count in expected_totals.items():
            with self.subTest(players=player_count):
                matches = generate_schedule(player_count, 6)
                self.assertEqual(len(matches), expected_match_count)
                stroman_matches = [
                    match
                    for match in matches
                    if "stroman" in (match["player1"], match["player2"])
                ]
                if player_count % 2:
                    self.assertEqual(len(stroman_matches), 1)
                    self.assertEqual(matches[-1], stroman_matches[0])
                else:
                    self.assertEqual(stroman_matches, [])

    def test_selected_player_gets_the_final_stroman_match(self):
        matches = generate_schedule(15, 4, stroman_player=6)

        self.assertEqual(matches[-1]["player1"], 6)
        self.assertEqual(matches[-1]["player2"], "stroman")

    def test_schedule_counts_round_fill_and_referee_balance(self):
        for player_count, requested_boards in (
            (4, 2), (5, 2), (6, 4), (15, 4), (19, 4), (19, 5), (30, 6)
        ):
            with self.subTest(players=player_count, boards=requested_boards):
                matches = generate_schedule(player_count, requested_boards)
                active_boards = min(requested_boards, max(1, player_count // 3))
                expected_match_count = (
                    player_count * 5 + player_count % 2
                ) // 2
                self.assertEqual(len(matches), expected_match_count)
                self.assertEqual(
                    {match["board"] for match in matches},
                    set(range(1, active_boards + 1)),
                )

                appearances = Counter(
                    player
                    for match in matches
                    for player in (match["player1"], match["player2"])
                    if isinstance(player, int)
                )
                self.assertEqual(set(appearances.values()), {5})

                round_matches = defaultdict(list)
                previous_games = {}
                referee_counts = Counter()
                for match in matches:
                    round_matches[match["round"]].append(match)
                    referee_counts[match["referee"]] += 1
                    if match["board"] in previous_games:
                        self.assertIn(match["referee"], previous_games[match["board"]])
                    previous_games[match["board"]] = (
                        match["player1"],
                        match["player2"],
                    )

                round_sizes = [
                    len(games) for games in round_matches.values()
                ]
                expected_remainder = expected_match_count % active_boards
                if expected_remainder:
                    self.assertEqual(round_sizes.count(expected_remainder), 1)
                self.assertTrue(
                    all(
                        size == active_boards or size == expected_remainder
                        for size in round_sizes
                    )
                )
                for games in round_matches.values():
                    playing = {
                        player
                        for game in games
                        for player in (game["player1"], game["player2"])
                        if isinstance(player, int)
                    }
                    game_players = [
                        player
                        for game in games
                        for player in (game["player1"], game["player2"])
                        if isinstance(player, int)
                    ]
                    self.assertEqual(len(game_players), len(set(game_players)))
                    referees = [game["referee"] for game in games]
                    self.assertEqual(len(referees), len(set(referees)))
                    self.assertFalse(set(referees) & playing)

                duty_counts = [
                    referee_counts.get(player, 0)
                    for player in range(player_count)
                ]
                self.assertLessEqual(max(duty_counts) - min(duty_counts), 1)

                stroman_indices = [
                    index
                    for index, match in enumerate(matches)
                    if "stroman" in (match["player1"], match["player2"])
                ]
                if player_count % 2:
                    self.assertTrue(stroman_indices)
                    self.assertEqual(stroman_indices, list(range(stroman_indices[0], len(matches))))
                    self.assertEqual(matches[-1]["player2"], "stroman")
                else:
                    self.assertFalse(stroman_indices)

    def test_maximum_supported_roster_uses_all_requested_blocks(self):
        matches = generate_schedule(128, 30)
        appearances = Counter(
            player
            for match in matches
            for player in (match["player1"], match["player2"])
            if isinstance(player, int)
        )
        rounds = Counter(match["round"] for match in matches)
        round_players = defaultdict(list)
        for match in matches:
            round_players[match["round"]].extend(
                player
                for player in (match["player1"], match["player2"])
                if isinstance(player, int)
            )
        self.assertEqual(len(matches), 320)
        self.assertEqual(set(appearances.values()), {5})
        self.assertEqual(
            [rounds[round_number] for round_number in range(1, 12)],
            [30] * 10 + [20],
        )
        self.assertTrue(
            all(len(players) == len(set(players)) for players in round_players.values())
        )

    def test_custom_match_counts_give_every_player_the_requested_appearances(self):
        for player_count, requested_boards, match_count in (
            (4, 2, 1),
            (4, 2, 20),
            (6, 4, 3),
            (15, 4, 7),
            (19, 5, 3),
            (5, 2, 7),
        ):
            with self.subTest(
                players=player_count,
                boards=requested_boards,
                matches=match_count,
            ):
                matches = generate_schedule(
                    player_count,
                    requested_boards,
                    match_count,
                )
                appearances = Counter(
                    player
                    for match in matches
                    for player in (match["player1"], match["player2"])
                    if isinstance(player, int)
                )
                round_players = defaultdict(list)
                for match in matches:
                    round_players[match["round"]].extend(
                        player
                        for player in (match["player1"], match["player2"])
                        if isinstance(player, int)
                    )
                self.assertEqual(set(appearances.values()), {match_count})
                self.assertEqual(
                    len(matches),
                    (player_count * match_count + player_count % 2) // 2,
                )
                self.assertTrue(
                    all(
                        len(players) == len(set(players))
                        for players in round_players.values()
                    )
                )


class SeasonStandingsHistoryTests(TestCase):
    def setUp(self):
        self.season = Season.objects.create(name="2026-2027")
        self.players = [
            Player.objects.create(name=name)
            for name in ("Alice", "Bob", "Carla", "Dirk")
        ]
        self.first = self.add_evening("2026-09-04", self.players)
        self.add_match(self.first, self.players[0], self.players[3], 3, 0)
        self.add_match(self.first, self.players[1], self.players[2], 2, 1)
        self.second = self.add_evening("2026-10-02", self.players[1:3])
        self.add_match(self.second, self.players[1], self.players[2], 3, 0)
        self.url = reverse("season_standings", args=[self.season.pk])

    def add_evening(self, date, players, season=None):
        evening = Evening.objects.create(
            season=season or self.season, date=date, board_count=2
        )
        for number, player in enumerate(players, start=1):
            Attendance.objects.create(
                evening=evening, player=player, draw_order=number
            )
        return evening

    def add_match(self, evening, player1, player2, legs1, legs2):
        match = Match.objects.create(
            evening=evening,
            number=evening.matches.count() + 1,
            round_number=1,
            board=1,
            player1=player1,
            player2=player2,
            referee=self.players[0],
        )
        MatchPlayerStats.objects.create(match=match, player=player1, legs_won=legs1)
        MatchPlayerStats.objects.create(match=match, player=player2, legs_won=legs2)
        return match

    def test_latest_standings_include_absent_players_and_position_changes(self):
        with self.assertNumQueries(4):
            rows = season_standings(self.season)
        self.assertEqual(
            [row["player"].name for row in rows], ["Bob", "Alice", "Carla", "Dirk"]
        )
        self.assertEqual([row["points"] for row in rows], [5, 3, 1, 0])
        self.assertEqual([row["position_change"] for row in rows], [1, -1, 0, 0])
        response = self.client.get(self.url)
        self.assertContains(response, "<th>Positie</th>")
        self.assertContains(response, ">+1</span>")
        self.assertContains(response, ">-1</span>")
        self.assertContains(response, 'aria-label="Positie gelijk gebleven">=</span>')
        self.assertContains(response, "Stand na speeldag 2 - 02/10/2026")
        self.assertContains(response, f'href="?evening={self.first.pk}&amp;ranking=points"')
        self.assertNotContains(response, "Volgende speeldag")
        overview = self.client.get(reverse("season_detail", args=[self.season.pk]))
        self.assertContains(overview, "<th>Positie</th>")
        self.assertContains(overview, ">+1</span>")

    def test_statistic_leaderboards_sort_by_requested_metric_and_keep_date_selection(self):
        stats = {
            "Alice": (2, 1, "100, 170", "12, 15"),
            "Bob": (1, 3, "120, 164", "9, 13"),
            "Carla": (3, 2, "167", "15"),
            "Dirk": (0, 0, "", ""),
        }
        for player in self.players:
            stat = MatchPlayerStats.objects.filter(
                match__evening=self.first, player=player
            ).first()
            scores_180, scores_171, finishes, least_darts = stats[player.name]
            stat.scores_180 = scores_180
            stat.scores_171 = scores_171
            stat.high_finishes = finishes
            stat.least_darts = least_darts
            stat.save()

        base_rows = season_standings(self.season, self.first)
        expected_orders = {
            "scores_180": ["Carla", "Alice", "Bob", "Dirk"],
            "scores_171": ["Bob", "Carla", "Alice", "Dirk"],
            "highest_finish": ["Alice", "Carla", "Bob", "Dirk"],
            "least_darts": ["Bob", "Alice", "Carla", "Dirk"],
        }
        for ranking, expected_names in expected_orders.items():
            with self.subTest(ranking=ranking):
                rows = sort_standings_for_ranking(base_rows, ranking)
                self.assertEqual(
                    [row["player"].name for row in rows], expected_names
                )
                response = self.client.get(
                    self.url, {"evening": self.first.pk, "ranking": ranking}
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["selected_ranking"], ranking)
                self.assertContains(response, f'href="?ranking={ranking}&amp;evening={self.first.pk}"')
                self.assertNotContains(response, "<th>Positie</th>")
                self.assertContains(response, expected_names[0])

        with self.assertRaisesMessage(ValueError, "Onbekend extra klassement"):
            sort_standings_for_ranking(base_rows, "unknown")

    def test_invalid_leaderboard_tab_returns_404(self):
        self.assertEqual(
            self.client.get(self.url, {"ranking": "unknown"}).status_code, 404
        )

    def test_first_day_excludes_later_results_and_marks_everyone_new(self):
        rows = season_standings(self.season, self.first)
        self.assertEqual(
            [row["player"].name for row in rows], ["Alice", "Bob", "Carla", "Dirk"]
        )
        self.assertEqual([row["points"] for row in rows], [3, 2, 1, 0])
        self.assertTrue(all(row["position_change"] is None for row in rows))
        self.assertEqual(rows[0]["refereed"], 2)
        response = self.client.get(self.url, {"evening": self.first.pk})
        self.assertContains(response, ">Nieuw</span>", count=4)
        self.assertContains(response, "Stand na speeldag 1 - 04/09/2026")
        self.assertContains(response, f'value="{self.first.pk}" selected')
        self.assertContains(response, f'href="?evening={self.second.pk}&amp;ranking=points"')
        self.assertNotContains(response, "Vorige speeldag")

    def test_new_players_are_excluded_from_earlier_days_and_can_push_others_down(self):
        newcomers = [Player.objects.create(name=f"Nieuw {number}") for number in range(3)]
        third = self.add_evening("2026-11-06", newcomers + [self.players[3]])
        for player in newcomers:
            match = self.add_match(third, player, self.players[3], 3, 0)
            MatchPlayerStats.objects.filter(match=match, player=player).update(scores_180=10)
        rows = season_standings(self.season, third)
        self.assertTrue(all(row["position_change"] is None for row in rows[:3]))
        self.assertEqual(rows[3]["player"], self.players[1])
        self.assertEqual(rows[3]["position_change"], -3)
        self.assertEqual(len(season_standings(self.season, self.second)), 4)
        response = self.client.get(self.url)
        self.assertContains(response, ">-3</span>")
        self.assertContains(response, ">Nieuw</span>", count=3)

    def test_incomplete_days_are_selectable_and_count_only_completed_matches(self):
        newcomer = Player.objects.create(name="Eva")
        third = self.add_evening("2026-11-06", [newcomer, self.players[0]])
        match = self.add_match(third, newcomer, self.players[0], 3, None)
        MatchPlayerStats.objects.filter(match=match, player=newcomer).update(scores_180=10)
        rows = season_standings(self.season, third)
        self.assertEqual([row["points"] for row in rows], [5, 3, 1, 0, 0])
        self.assertEqual([row["position_change"] for row in rows], [0, 0, 0, None, -1])
        response = self.client.get(self.url, {"evening": third.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_evening"], third)
        self.assertContains(response, "nog niet alle uitslagen zijn ingevuld")

    def test_days_are_ordered_by_date_then_id_not_creation_order(self):
        earlier = self.add_evening("2026-08-01", [self.players[3], self.players[0]])
        self.add_match(earlier, self.players[3], self.players[0], 3, 0)
        same_date = self.add_evening("2026-09-04", self.players[:2])
        self.add_match(same_date, self.players[1], self.players[0], 3, 0)
        first_rows = season_standings(self.season, self.first)
        self.assertEqual(sum(row["points"] for row in first_rows), 9)
        same_date_rows = season_standings(self.season, same_date)
        self.assertEqual(sum(row["points"] for row in same_date_rows), 12)
        response = self.client.get(self.url, {"evening": same_date.pk})
        self.assertEqual(response.context["previous_evening"], self.first)
        self.assertEqual(response.context["next_evening"], self.second)
        self.assertEqual(response.context["selected_number"], 3)

    def test_result_corrections_recalculate_historical_standings(self):
        MatchPlayerStats.objects.filter(
            match__evening=self.first, player=self.players[1]
        ).update(scores_180=5)
        first_rows = season_standings(self.season, self.first)
        self.assertEqual(first_rows[0]["player"], self.players[1])
        latest_rows = season_standings(self.season)
        self.assertEqual(latest_rows[0]["points"], 10)
        self.assertEqual(latest_rows[0]["position_change"], 0)

    def test_invalid_or_foreign_day_returns_404(self):
        other_season = Season.objects.create(name="Ander seizoen")
        foreign = self.add_evening("2026-10-02", self.players, season=other_season)
        match = self.add_match(foreign, self.players[3], self.players[0], 3, 0)
        MatchPlayerStats.objects.filter(match=match, player=self.players[3]).update(scores_180=20)
        for value in ("invalid", "-1", "999999", str(foreign.pk)):
            with self.subTest(evening=value):
                self.assertEqual(
                    self.client.get(self.url, {"evening": value}).status_code, 404
                )
        with self.assertRaisesMessage(ValueError, "hoort niet bij dit seizoen"):
            season_standings(self.season, foreign)
        self.assertEqual(
            [row["points"] for row in season_standings(self.season)], [5, 3, 1, 0]
        )

    def test_empty_season_and_empty_day_render_without_navigation_errors(self):
        season = Season.objects.create(name="Leeg seizoen")
        url = reverse("season_standings", args=[season.pk])
        response = self.client.get(url)
        self.assertContains(response, "Nog geen spelers om te tonen.")
        self.assertContains(response, 'colspan="13"')
        self.assertNotContains(response, 'id="standings-evening"')
        self.assertEqual(response.context["standings"], [])
        evening = self.add_evening("2026-11-06", [], season=season)
        response = self.client.get(url)
        self.assertEqual(response.context["selected_evening"], evening)
        self.assertContains(response, "Nog geen spelers om te tonen.")


class CompetitionFlowTests(TestCase):
    def setUp(self):
        self.season = Season.objects.create(name="2026-2027")
        self.players = [
            Player.objects.create(name=f"Speler {number:02}")
            for number in range(1, 16)
        ]
        self.evening = create_evening(
            season=self.season,
            date="2026-10-01",
            board_count=4,
            players=self.players,
        )

    def test_rules_page_is_available_from_navigation_and_explains_scoring(self):
        response = self.client.get(reverse("rules"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<h1>Spelregels</h1>")
        self.assertContains(response, "1 punt per gewonnen leg")
        self.assertContains(response, "finish van 161, 164, 167 of 170")
        self.assertContains(response, "Stroman")
        self.assertContains(response, "Meeste punten")
        home_response = self.client.get(reverse("home"))
        self.assertContains(home_response, f'href="{reverse("rules")}">Spelregels</a>')

    def test_season_standings_use_the_requested_tie_break_order(self):
        players_by_name = {
            name: Player.objects.create(name=f"Tiebreak {name}")
            for name in ("A", "B", "C", "D", "E")
        }
        match_data = {
            "A": [(2, "100", 2, 2)],
            "B": [(3, "100", 4, 0)],
            "C": [(3, "", 2, 0), (3, "", 3, 0)],
            "D": [(3, "120", 3, 1)],
            "E": [(3, "120", 4, 0)],
        }
        for index, (name, games) in enumerate(match_data.items(), start=1):
            player = players_by_name[name]
            evening = Evening.objects.create(
                season=self.season,
                date=f"2026-11-{index:02}",
                board_count=2,
                match_count=len(games),
            )
            Attendance.objects.create(
                evening=evening,
                player=player,
                draw_order=1,
            )
            for number, (legs, finish, scores_180, scores_171) in enumerate(
                games, start=1
            ):
                match = Match.objects.create(
                    evening=evening,
                    number=number,
                    round_number=number,
                    board=1,
                    player1=player,
                )
                MatchPlayerStats.objects.create(
                    match=match,
                    player=player,
                    legs_won=legs,
                    high_finishes=finish,
                    scores_180=scores_180,
                    scores_171=scores_171,
                )

        standings = season_standings(self.season)

        self.assertEqual(
            [row["player"].name for row in standings[:5]],
            [
                "Tiebreak E",
                "Tiebreak D",
                "Tiebreak B",
                "Tiebreak A",
                "Tiebreak C",
            ],
        )

    def test_points_include_only_specified_bonus_events_and_not_stroman_legs(self):
        regular_match = self.evening.matches.filter(player2__isnull=False).first()
        regular_stat = MatchPlayerStats.objects.get(
            match=regular_match,
            player=regular_match.player1,
        )
        regular_stat.legs_won = 2
        regular_stat.scores_180 = 2
        regular_stat.scores_177 = 10
        regular_stat.scores_174 = 10
        regular_stat.scores_171 = 3
        regular_stat.high_finishes = (
            "100, 160, 161, 162, 163, 164, 165, 166, 167, 168, 169, 170"
        )
        regular_stat.least_darts = "11, 12"
        regular_stat.save()
        self.assertEqual(regular_stat.bonus_points, 15)
        self.assertEqual(regular_stat.points, 17)

        stroman_match = self.evening.matches.filter(player2__isnull=True).first()
        stroman_stat = MatchPlayerStats.objects.get(
            match=stroman_match,
            player=stroman_match.player1,
        )
        stroman_stat.legs_won = 3
        stroman_stat.scores_180 = 1
        stroman_stat.scores_171 = 1
        stroman_stat.high_finishes = "100, 170"
        stroman_stat.save()
        self.assertEqual(stroman_stat.bonus_points, 5)
        self.assertEqual(stroman_stat.points, 5)

    def test_new_evening_form_creates_schedule_in_draw_order(self):
        selected_players = [self.players[number] for number in (4, 2, 8, 0)]
        excluded_player = Player.objects.create(name="Niet aanwezig")
        draw_order = [player.id for player in selected_players]
        response = self.client.post(
            reverse("new_evening"),
            {
                "season": self.season.id,
                "date": "01/11/2026",
                "board_count": "30",
                "match_count": "3",
                "players": [str(player.id) for player in selected_players],
                "draw_order": json.dumps(draw_order),
            },
        )
        evening = Evening.objects.get(season=self.season, date="2026-11-01")
        self.assertRedirects(response, reverse("evening_detail", args=[evening.id]))
        self.assertEqual(
            list(evening.attendances.values_list("player_id", flat=True)),
            draw_order,
        )
        self.assertEqual(evening.board_count, 30)
        self.assertEqual(evening.match_count, 3)
        self.assertNotIn(excluded_player.id, draw_order)
        self.assertEqual(evening.matches.count(), 6)
        appearances = Counter(
            player_id
            for match in evening.matches.all()
            for player_id in (match.player1_id, match.player2_id)
            if player_id is not None
        )
        self.assertEqual(set(appearances.values()), {3})

    def test_new_evening_reports_unavailable_schedule_without_creating_evening(self):
        selected_players = [*self.players, Player.objects.create(name="Speler 16")]
        draw_order = [player.id for player in selected_players]

        response = self.client.post(
            reverse("new_evening"),
            {
                "season": self.season.id,
                "date": "03/11/2026",
                "board_count": "5",
                "match_count": "5",
                "players": [str(player.id) for player in selected_players],
                "draw_order": json.dumps(draw_order),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "kan geen geldig schema worden gemaakt")
        self.assertFalse(Evening.objects.filter(date="2026-11-03").exists())

    def test_stroman_player_is_required_and_used_for_odd_evening(self):
        selected_players = self.players[:5]
        data = {
            "season": self.season.id,
            "date": "02/11/2026",
            "board_count": "2",
            "match_count": "5",
            "players": [str(player.id) for player in selected_players],
            "draw_order": json.dumps([player.id for player in selected_players]),
        }

        missing_stroman = self.client.post(reverse("new_evening"), data)
        self.assertEqual(missing_stroman.status_code, 200)
        self.assertContains(missing_stroman, "Kies de speler die de stroman speelt.")
        self.assertFalse(Evening.objects.filter(date="2026-11-02").exists())

        stroman = selected_players[3]
        data["stroman_player"] = str(stroman.id)
        response = self.client.post(reverse("new_evening"), data)

        evening = Evening.objects.get(date="2026-11-02")
        self.assertRedirects(response, reverse("evening_detail", args=[evening.id]))
        final_match = evening.matches.order_by("-number").first()
        self.assertTrue(final_match.is_phantom_match)
        self.assertEqual(final_match.player1_id, stroman.id)
        self.assertEqual(
            evening.matches.count(),
            13,
        )
        response = self.client.get(reverse("evening_detail", args=[evening.id]))
        self.assertTrue(response.context["schedule_audit"]["valid"])
        self.assertEqual(response.context["schedule_audit"]["expected_matches"], 13)
        stroman_row = next(
            row
            for row in response.context["match_audit"]
            if row["attendance"].player_id == stroman.id
        )
        self.assertEqual(stroman_row["matches"], 5)
        self.assertEqual(stroman_row["stroman_matches"], 1)
        self.assertFalse(
            any(
                stroman.id in {match.player1_id, match.player2_id}
                for match in evening.matches.filter(
                    round_number=final_match.round_number,
                    player2__isnull=False,
                )
            )
        )
        response = self.client.post(
            reverse("regenerate_schedule", args=[evening.id])
        )
        self.assertRedirects(response, reverse("evening_detail", args=[evening.id]))
        final_match = evening.matches.order_by("-number").first()
        self.assertEqual(final_match.player1_id, stroman.id)

    def test_evening_form_lists_active_players_as_unchecked_options(self):
        response = self.client.get(reverse("new_evening"))
        self.assertEqual(response.status_code, 200)
        for player in self.players:
            self.assertContains(response, player.name)
        self.assertContains(response, "name=\"players\"")
        self.assertContains(response, "id_draw_order")
        self.assertContains(response, "Aanwezige spelers")
        self.assertContains(response, 'placeholder="dd/MM/yyyy"')
        self.assertContains(response, 'id="board-capacity-note"')
        self.assertContains(response, "Voor 4 blokken zijn minimaal 12 deelnemers nodig.")
        self.assertContains(response, 'name="match_count"')
        self.assertContains(response, 'value="5"')

    def test_evening_form_rejects_dates_outside_dutch_format(self):
        data = {
            "season": self.season.id,
            "date": "2026-11-01",
            "board_count": "4",
            "match_count": "5",
            "players": [str(player.id) for player in self.players[:4]],
            "draw_order": json.dumps([player.id for player in self.players[:4]]),
        }
        response = self.client.post(reverse("new_evening"), data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Evening.objects.filter(date="2026-11-01").exists())
        self.assertContains(response, "dd/MM/yyyy")

    def test_player_name_can_be_edited_without_breaking_existing_matches(self):
        player = self.players[0]
        match = Match.objects.filter(evening=self.evening, player1=player).first()
        response = self.client.post(
            reverse("edit_player", args=[player.id]),
            {"name": "Nieuwe spelersnaam", "active": "on"},
        )
        self.assertRedirects(response, reverse("players"))
        player.refresh_from_db()
        match.refresh_from_db()
        self.assertEqual(player.name, "Nieuwe spelersnaam")
        self.assertEqual(match.player1_id, player.id)
        self.assertEqual(match.player1.name, "Nieuwe spelersnaam")

    def test_player_detail_shows_match_history_opponents_and_statistics(self):
        player = self.players[0]
        match = Match.objects.filter(
            evening=self.evening, player1=player, player2__isnull=False
        ).first()
        result_response = self.client.post(
            reverse("edit_match", args=[match.id]),
            {
                "p1_legs": "2",
                "p1_high_finishes": "100, 120",
                "p1_171": "1",
                "p1_180": "4",
                "p1_least_darts": "13, 15",
                "p2_legs": "1",
                "p2_high_finishes": "",
                "p2_171": "0",
                "p2_180": "0",
                "p2_least_darts": "",
            },
        )
        self.assertRedirects(
            result_response, reverse("evening_detail", args=[self.evening.id])
        )

        response = self.client.get(reverse("player_detail", args=[player.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["matches"]), 5)
        self.assertEqual(response.context["played_count"], 1)
        self.assertEqual(response.context["opponents"], [(match.player2, 1)])
        self.assertEqual(response.context["totals"]["high_finishes"], 2)
        self.assertEqual(response.context["totals"]["least_darts"], 2)
        self.assertEqual(response.context["totals"]["scores_171"], 1)
        self.assertEqual(response.context["totals"]["scores_180"], 4)
        self.assertNotContains(response, "174-worpen")
        self.assertNotContains(response, "177-worpen")
        self.assertEqual(response.context["high_finish_values"], [100, 120])
        self.assertEqual(response.context["least_darts_values"], [13, 15])
        match_row = next(
            row for row in response.context["matches"] if row["match"].id == match.id
        )
        self.assertEqual(match_row["high_finishes"], [100, 120])
        self.assertContains(response, reverse("edit_match", args=[match.id]))
        self.assertContains(response, "2 - 1")
        self.assertContains(response, "100, 120")
        self.assertContains(response, "13, 15")
        self.assertContains(response, "HF gegooid")
        self.assertContains(response, "Nog niet gespeeld")
        self.assertContains(response, "Minste pijlen per leg")
        self.assertContains(response, "Scheidsbeurten")

    def test_player_names_link_to_player_overview_from_roster_and_standings(self):
        player = self.players[0]

        roster_response = self.client.get(reverse("players"))
        standings_response = self.client.get(
            reverse("season_standings", args=[self.season.id])
        )

        player_url = reverse("player_detail", args=[player.id])
        self.assertContains(roster_response, f'href="{player_url}">{player.name}</a>')
        self.assertContains(standings_response, f'href="{player_url}">{player.name}</a>')
        for score in (171, 180):
            self.assertContains(standings_response, f"<th>{score}</th>")
        self.assertNotContains(standings_response, "<th>174</th>")
        self.assertNotContains(standings_response, "<th>177</th>")
        self.assertNotContains(standings_response, "<progress")

    def test_player_edit_rejects_duplicate_name_case_insensitively(self):
        player = self.players[0]
        response = self.client.post(
            reverse("edit_player", args=[player.id]),
            {"name": self.players[1].name.upper(), "active": "on"},
        )
        self.assertEqual(response.status_code, 200)
        player.refresh_from_db()
        self.assertEqual(player.name, "Speler 01")

    def test_player_and_board_bounds_are_enforced(self):
        data = {
            "season": self.season.id,
            "date": "01/11/2026",
            "board_count": "1",
            "match_count": "5",
            "players": [str(player.id) for player in self.players[:3]],
            "draw_order": json.dumps([player.id for player in self.players[:3]]),
        }
        response = self.client.post(reverse("new_evening"), data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Evening.objects.filter(date="2026-11-01").exists())

        data["board_count"] = "4"
        data["match_count"] = "0"
        response = self.client.post(reverse("new_evening"), data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Evening.objects.filter(date="2026-11-01").exists())

        data["match_count"] = "21"
        response = self.client.post(reverse("new_evening"), data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Evening.objects.filter(date="2026-11-01").exists())

        data["match_count"] = "5"
        data["board_count"] = "31"
        data["players"] = [str(player.id) for player in self.players[:4]]
        data["draw_order"] = json.dumps([player.id for player in self.players[:4]])
        response = self.client.post(reverse("new_evening"), data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Evening.objects.filter(date="2026-11-01").exists())

    def test_evening_has_five_games_per_player_and_one_stroman_match(self):
        matches = list(self.evening.matches.all())
        self.assertEqual(len(matches), 38)
        self.assertEqual(sum(match.is_phantom_match for match in matches), 1)
        self.assertEqual(self.evening.attendances.count(), 15)
        for match in matches:
            self.assertGreaterEqual(match.board, 1)
            self.assertLessEqual(match.board, 4)

    def test_evening_uses_all_four_requested_boards(self):
        evening = create_evening(
            season=self.season,
            date="2026-10-02",
            board_count=4,
            players=self.players,
        )
        self.assertEqual(
            set(evening.matches.values_list("board", flat=True)),
            {1, 2, 3, 4},
        )

    def test_unplayed_evening_schedule_can_be_rebuilt_with_full_rounds(self):
        old_match_ids = set(self.evening.matches.values_list("id", flat=True))
        response = self.client.post(
            reverse("regenerate_schedule", args=[self.evening.id])
        )
        self.assertRedirects(
            response,
            reverse("evening_detail", args=[self.evening.id]),
        )
        matches = list(
            self.evening.matches.order_by("number").values(
                "id", "board", "round_number"
            )
        )
        self.assertEqual(len(matches), 38)
        self.assertTrue(old_match_ids.isdisjoint({match["id"] for match in matches}))
        self.assertEqual(
            set(match["board"] for match in matches),
            {1, 2, 3, 4},
        )
        self.assertEqual(
            max(Counter(match["round_number"] for match in matches).values()),
            4,
        )

    def test_schedule_rebuild_is_blocked_after_results_are_entered(self):
        stat = MatchPlayerStats.objects.filter(match__evening=self.evening).first()
        stat.legs_won = 2
        stat.save()
        match_count = self.evening.matches.count()

        response = self.client.post(
            reverse("regenerate_schedule", args=[self.evening.id])
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(
            response,
            "Een schema met ingevoerde uitslagen",
            status_code=400,
        )
        self.assertEqual(self.evening.matches.count(), match_count)

    def test_evening_can_be_deleted_with_its_matches_and_attendance(self):
        delete_url = reverse("delete_evening", args=[self.evening.id])
        confirm = self.client.get(delete_url)
        self.assertEqual(confirm.status_code, 200)
        self.assertContains(confirm, "Dit kan niet ongedaan worden gemaakt")
        self.assertTrue(Evening.objects.filter(pk=self.evening.id).exists())

        response = self.client.post(delete_url)
        self.assertRedirects(response, reverse("season_detail", args=[self.season.id]))
        self.assertFalse(Evening.objects.filter(pk=self.evening.id).exists())
        self.assertFalse(Match.objects.filter(evening_id=self.evening.id).exists())
        self.assertFalse(Attendance.objects.filter(evening_id=self.evening.id).exists())
        self.assertTrue(Season.objects.filter(pk=self.season.id).exists())

    def test_season_can_be_deleted_with_competition_data_but_players_remain(self):
        season_id = self.season.id
        evening_id = self.evening.id
        match_ids = list(self.evening.matches.values_list("id", flat=True))
        player_ids = [player.id for player in self.players]
        delete_url = reverse("delete_season", args=[season_id])

        confirm = self.client.get(delete_url)
        self.assertEqual(confirm.status_code, 200)
        self.assertContains(confirm, "Alle avonden, wedstrijden en uitslagen")
        self.assertTrue(Season.objects.filter(pk=season_id).exists())

        response = self.client.post(delete_url)

        self.assertRedirects(response, reverse("seasons"))
        self.assertFalse(Season.objects.filter(pk=season_id).exists())
        self.assertFalse(Evening.objects.filter(pk=evening_id).exists())
        self.assertFalse(Match.objects.filter(pk__in=match_ids).exists())
        self.assertFalse(MatchPlayerStats.objects.filter(match_id__in=match_ids).exists())
        self.assertFalse(Attendance.objects.filter(evening_id=evening_id).exists())
        self.assertEqual(Player.objects.filter(pk__in=player_ids).count(), len(player_ids))

    def test_results_can_be_entered_corrected_and_reflected_in_standings(self):
        match = Match.objects.filter(evening=self.evening, player2__isnull=False).first()
        result_url = reverse("edit_match", args=[match.id])
        form_response = self.client.get(result_url)
        self.assertEqual(form_response.status_code, 200)
        self.assertContains(form_response, 'class="result-entry-table"')
        self.assertContains(form_response, "HF<br>(finishwaarde)")
        self.assertContains(form_response, "MP<br>(pijlen)")
        self.assertContains(form_response, match.player1.name)
        self.assertContains(form_response, match.player2.name)
        self.assertContains(form_response, 'name="p1_legs"')
        self.assertContains(form_response, 'name="p2_legs"')
        self.assertContains(form_response, 'name="p1_171"')
        self.assertContains(form_response, 'name="p1_180"')
        self.assertNotContains(form_response, 'name="p1_174"')
        self.assertNotContains(form_response, 'name="p1_177"')
        self.assertContains(form_response, "HF 74, 120")
        stats_before = {
            stat.player_id: stat
            for stat in match.stats.all()
        }
        stats_before[match.player1_id].scores_174 = 2
        stats_before[match.player1_id].scores_177 = 3
        stats_before[match.player1_id].save()
        result = {
            "p1_legs": "2", "p1_high_finishes": "100, 120",
            "p1_180": "1", "p1_171": "1",
            "p1_least_darts": "13, 15",
            "p2_legs": "1", "p2_high_finishes": "",
            "p2_180": "0", "p2_171": "0",
            "p2_least_darts": "",
        }
        response = self.client.post(result_url, result)
        self.assertRedirects(response, reverse("evening_detail", args=[self.evening.id]))
        match.refresh_from_db()
        rows = build_standings(
            [record.player for record in self.evening.attendances.select_related("player")],
            list(self.evening.matches.select_related("player1", "player2", "referee").prefetch_related("stats")),
        )
        first_row = next(row for row in rows if row["player"].id == match.player1_id)
        self.assertEqual(first_row["points"], 6)
        self.assertEqual(first_row["legs_for"], 2)
        self.assertEqual(first_row["legs_against"], 1)
        self.assertEqual(first_row["legs_balance"], 1)
        self.assertEqual(first_row["scores_171"], 1)
        self.assertEqual(first_row["scores_180"], 1)
        stats_before[match.player1_id].refresh_from_db()
        self.assertEqual(stats_before[match.player1_id].scores_174, 2)
        self.assertEqual(stats_before[match.player1_id].scores_177, 3)
        evening_response = self.client.get(
            reverse("evening_detail", args=[self.evening.id])
        )
        current_rows = evening_response.context["standings"]
        highest_points = max(row["points"] for row in current_rows)
        first_current_row = next(
            row for row in current_rows if row["player"].id == match.player1_id
        )
        self.assertEqual(first_current_row["points_progress"], 100)
        self.assertEqual(
            first_current_row["matches_progress"],
            round(
                first_current_row["matches_played"]
                * 100
                / first_current_row["matches_scheduled"]
            ),
        )
        self.assertGreater(highest_points, 0)

        result.update({"p1_legs": "1", "p2_legs": "2"})
        self.client.post(result_url, result)
        match.refresh_from_db()
        rows = build_standings(
            [record.player for record in self.evening.attendances.select_related("player")],
            list(self.evening.matches.select_related("player1", "player2", "referee").prefetch_related("stats")),
        )
        first_row = next(row for row in rows if row["player"].id == match.player1_id)
        self.assertEqual(first_row["points"], 5)
        self.assertEqual(first_row["legs_against"], 2)
        stat = MatchPlayerStats.objects.get(match=match, player=match.player1)
        self.assertEqual(stat.least_darts, "13, 15")
        self.assertEqual(first_row["least_darts"], 13)

    def test_least_darts_accepts_multiple_valid_legs_and_rejects_invalid_values(self):
        match = Match.objects.filter(evening=self.evening, player2__isnull=False).first()
        result = {
            "p1_legs": "2", "p1_high_finishes": "",
            "p1_180": "0", "p1_171": "0",
            "p1_least_darts": "13,15",
            "p2_legs": "1", "p2_high_finishes": "",
            "p2_180": "0", "p2_171": "0",
            "p2_least_darts": "",
        }
        response = self.client.post(reverse("edit_match", args=[match.id]), result)
        self.assertRedirects(response, reverse("evening_detail", args=[self.evening.id]))
        stat = MatchPlayerStats.objects.get(match=match, player=match.player1)
        self.assertEqual(stat.least_darts, "13, 15")
        self.assertEqual(stat.bonus_points, 0)

        result["p1_least_darts"] = "13, 100"
        response = self.client.post(reverse("edit_match", args=[match.id]), result)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "tussen 1 en 99")

        result["p1_least_darts"] = "13, 14, 15, 12"
        response = self.client.post(reverse("edit_match", args=[match.id]), result)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "maximaal drie legs")

    def test_phantom_match_result_form_shows_one_player_row(self):
        match = self.evening.matches.filter(player2__isnull=True).first()
        response = self.client.get(reverse("edit_match", args=[match.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="p1_legs"')
        self.assertNotContains(response, 'name="p2_legs"')
        self.assertContains(response, "Stroman")
        self.assertContains(response, "result-entry-table")

    def test_evening_and_print_pages_render(self):
        response = self.client.get(reverse("evening_detail", args=[self.evening.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Wedstrijdschema")
        self.assertContains(response, "Tussenstand")
        self.assertContains(response, "Wedstrijden ingepland")
        self.assertContains(response, "Scheids")
        self.assertContains(response, "Controle")
        audit = response.context["match_audit"]
        self.assertEqual(len(audit), self.evening.attendances.count())
        self.assertEqual({row["matches"] for row in audit}, {5})
        self.assertTrue(response.context["schedule_audit"]["valid"])
        self.assertEqual(response.context["schedule_audit"]["actual_matches"], 38)
        self.assertEqual(response.context["schedule_audit"]["expected_matches"], 38)
        self.assertTrue(
            all(row["matches_scheduled"] == 5 for row in response.context["standings"])
        )
        self.assertTrue(
            all(row["points_progress"] == 0 for row in response.context["standings"])
        )
        self.assertTrue(
            all(row["matches_progress"] == 0 for row in response.context["standings"])
        )
        referee_counts = Counter(
            referee_id
            for referee_id in self.evening.matches.values_list(
                "referee_id", flat=True
            )
            if referee_id is not None
        )
        self.assertEqual(
            {
                row["attendance"].player_id: row["referees"]
                for row in audit
            },
            {
                attendance.player_id: referee_counts.get(attendance.player_id, 0)
                for attendance in self.evening.attendances.all()
            },
        )
        response_content = response.content.decode()
        self.assertGreater(
            response_content.index("<h2>Controle</h2>"),
            response_content.index("<h2>Wedstrijdschema</h2>"),
        )
        self.assertContains(response, "01/10/2026")
        standings_response = self.client.get(
            reverse("evening_standings", args=[self.evening.id])
        )
        self.assertEqual(standings_response.status_code, 200)
        self.assertContains(standings_response, "Tussenstand van de avond")
        self.assertContains(standings_response, "Klassement van de avond")
        self.assertNotContains(standings_response, "<h2>Wedstrijdschema</h2>")
        self.assertNotContains(standings_response, "<th>Scheids</th>")
        self.assertContains(standings_response, "<progress", html=False)
        self.assertContains(standings_response, 'class="evening-standing-table"')
        self.assertContains(standings_response, 'class="standing-progress-cell"')
        self.assertContains(standings_response, "Punten: ")
        self.assertContains(standings_response, "Wedstrijden: ")
        self.assertContains(standings_response, "Legsaldo")
        self.assertNotContains(standings_response, "<th>174</th>")
        self.assertNotContains(standings_response, "<th>177</th>")
        self.assertContains(standings_response, 'class="active" aria-current="page">Tussenstand')
        print_response = self.client.get(reverse("print_evening", args=[self.evening.id]))
        self.assertEqual(print_response.status_code, 200)
        self.assertContains(print_response, "Wedstrijdbriefjes")
        self.assertContains(print_response, "Legs")
        self.assertContains(print_response, "HF")
        self.assertContains(print_response, "MP")
        self.assertContains(print_response, "Scheidsrechter:")
        self.assertNotContains(print_response, "stallion_bullets_logo.png")
        self.assertNotContains(print_response, "<td>0</td>")
        self.assertContains(print_response, "01/10/2026")

    def test_print_slip_includes_recorded_player_statistics(self):
        match = self.evening.matches.filter(player2__isnull=False).first()
        stat = MatchPlayerStats.objects.get(match=match, player=match.player1)
        stat.legs_won = 2
        stat.scores_171 = 1
        stat.scores_174 = 2
        stat.scores_177 = 3
        stat.scores_180 = 4
        stat.high_finishes = "100, 120"
        stat.least_darts = "13, 15"
        stat.save()

        response = self.client.get(reverse("print_evening", args=[self.evening.id]))

        self.assertContains(
            response,
            f"<th>{match.player1.name}</th>",
            html=True,
        )
        self.assertContains(response, "13, 15")
        self.assertContains(response, "Scheidsrechter:")
        self.assertContains(response, f"Wedstrijd: <b>{match.number}</b>", html=True)
        self.assertContains(response, "<td>2</td><td>1</td><td>4</td><td>2</td><td>13, 15</td>", html=True)
        self.assertNotContains(response, "<th>174</th>")
        self.assertNotContains(response, "<th>177</th>")
