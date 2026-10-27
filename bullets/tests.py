import json
from collections import Counter, defaultdict

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import Attendance, Evening, Match, MatchPlayerStats, Player, Season
from .schedule import generate_schedule
from .services import build_standings, create_evening


class ScheduleTests(SimpleTestCase):
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

    def test_evening_form_lists_active_players_as_unchecked_options(self):
        response = self.client.get(reverse("new_evening"))
        self.assertEqual(response.status_code, 200)
        for player in self.players:
            self.assertContains(response, player.name)
        self.assertContains(response, "name=\"players\"")
        self.assertContains(response, "id_draw_order")
        self.assertContains(response, "Aanwezige spelers")
        self.assertContains(response, 'placeholder="dd/MM/yyyy"')
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

    def test_results_can_be_entered_corrected_and_reflected_in_standings(self):
        match = Match.objects.filter(evening=self.evening, player2__isnull=False).first()
        result_url = reverse("edit_match", args=[match.id])
        form_response = self.client.get(result_url)
        self.assertEqual(form_response.status_code, 200)
        self.assertContains(form_response, 'class="result-entry-table"')
        self.assertContains(form_response, "HF<br>(waarden 100+)")
        self.assertContains(form_response, "MP<br>(≤15)")
        self.assertContains(form_response, match.player1.name)
        self.assertContains(form_response, match.player2.name)
        self.assertContains(form_response, 'name="p1_legs"')
        self.assertContains(form_response, 'name="p2_legs"')
        self.assertContains(form_response, "MP 13, 15")
        result = {
            "p1_legs": "2", "p1_high_finishes": "100, 120",
            "p1_180": "1", "p1_177": "0", "p1_174": "0", "p1_171": "0",
            "p1_least_darts": "13, 15",
            "p2_legs": "1", "p2_high_finishes": "",
            "p2_180": "0", "p2_177": "0", "p2_174": "0", "p2_171": "0",
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
        self.assertEqual(first_row["points"], 7)
        self.assertEqual(first_row["legs_for"], 2)
        self.assertEqual(first_row["legs_against"], 1)

        result.update({"p1_legs": "1", "p2_legs": "2"})
        self.client.post(result_url, result)
        match.refresh_from_db()
        rows = build_standings(
            [record.player for record in self.evening.attendances.select_related("player")],
            list(self.evening.matches.select_related("player1", "player2", "referee").prefetch_related("stats")),
        )
        first_row = next(row for row in rows if row["player"].id == match.player1_id)
        self.assertEqual(first_row["points"], 6)
        self.assertEqual(first_row["legs_against"], 2)
        stat = MatchPlayerStats.objects.get(match=match, player=match.player1)
        self.assertEqual(stat.least_darts, "13, 15")
        self.assertEqual(first_row["least_darts"], 13)

    def test_least_darts_accepts_multiple_valid_legs_and_rejects_invalid_values(self):
        match = Match.objects.filter(evening=self.evening, player2__isnull=False).first()
        result = {
            "p1_legs": "2", "p1_high_finishes": "",
            "p1_180": "0", "p1_177": "0", "p1_174": "0", "p1_171": "0",
            "p1_least_darts": "13,15",
            "p2_legs": "1", "p2_high_finishes": "",
            "p2_180": "0", "p2_177": "0", "p2_174": "0", "p2_171": "0",
            "p2_least_darts": "",
        }
        response = self.client.post(reverse("edit_match", args=[match.id]), result)
        self.assertRedirects(response, reverse("evening_detail", args=[self.evening.id]))
        stat = MatchPlayerStats.objects.get(match=match, player=match.player1)
        self.assertEqual(stat.least_darts, "13, 15")
        self.assertEqual(stat.bonus_points, 2)

        result["p1_least_darts"] = "13, 16"
        response = self.client.post(reverse("edit_match", args=[match.id]), result)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "tussen 1 en 15 pijlen")

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
        self.assertContains(response, "<td>2</td><td>1</td><td>2</td><td>3</td><td>4</td><td>2</td><td>13, 15</td>", html=True)
