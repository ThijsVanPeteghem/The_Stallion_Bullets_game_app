from collections import Counter
import heapq
import logging
import random
from itertools import combinations

from ortools.sat.python import cp_model


logger = logging.getLogger(__name__)


class ScheduleError(ValueError):
    pass


class StromanSelectionError(ScheduleError):
    pass


class _ScheduledPair:
    def __init__(self, players, player_rounds):
        self.players = tuple(players)
        self.player_rounds = player_rounds

    def __iter__(self):
        return iter(self.players)

    def __getitem__(self, index):
        return self.players[index]

    def __len__(self):
        return len(self.players)


def expected_match_count(player_count, match_count):
    return (player_count * match_count + 1) // 2


def _pairings(player_count, match_count=5, unmatched_player=0, seed=None):
    has_bye = player_count % 2 == 1
    ghost = player_count if has_bye else None
    participant_count = player_count + int(has_bye)
    circle = list(range(participant_count))
    round_count = participant_count - 1
    factors = []

    for _ in range(round_count):
        games = []
        bye = None
        for index in range(participant_count // 2):
            left = circle[index]
            right = circle[participant_count - 1 - index]
            if ghost in (left, right):
                bye = right if left == ghost else left
            else:
                games.append(tuple(sorted((left, right))))
        factors.append((games, bye))
        circle = [circle[0], circle[-1], *circle[1:-1]]

    if seed is not None:
        random.Random(seed).shuffle(factors)
    start = 0
    if has_bye and match_count % 2:
        start = next(
            offset
            for offset in range(round_count)
            if factors[(offset + match_count - 1) % round_count][1]
            == unmatched_player
        )
    elif not has_bye:
        start = unmatched_player % round_count

    selected_factors = [
        factors[(start + round_index) % round_count]
        for round_index in range(match_count)
    ]
    pairs = []
    for pair_start in range(0, match_count, 2):
        first_round = pair_start + 1
        first_games, first_bye = selected_factors[pair_start]
        pairs.extend(
            _ScheduledPair(game, {player: first_round for player in game})
            for game in first_games
        )
        if pair_start + 1 < match_count:
            second_round = first_round + 1
            second_games, second_bye = selected_factors[pair_start + 1]
            if has_bye:
                pairs.append(
                    _ScheduledPair(
                        tuple(sorted((first_bye, second_bye))),
                        {first_bye: first_round, second_bye: second_round},
                    )
                )
            pairs.extend(
                _ScheduledPair(game, {player: second_round for player in game})
                for game in second_games
            )
        elif has_bye:
            pairs.append(
                _ScheduledPair(
                    (first_bye, "stroman"),
                    {first_bye: first_round, "stroman": first_round + 1},
                )
            )
    return pairs


def _select_disjoint_games(games, count, rng):
    for _ in range(20):
        candidates = list(games)
        rng.shuffle(candidates)
        selected = []
        playing = set()
        for game in candidates:
            participants = set(game)
            if participants & playing:
                continue
            selected.append(game)
            playing.update(participants)
            if len(selected) == count:
                return selected
    raise ScheduleError("Er kon geen geldige ronde met unieke spelers worden samengesteld.")


def _assign_wave(boards, games, previous_games, playing, referee_counts, rng):
    available_by_board = {}
    for board in boards:
        previous = previous_games[board]
        available_by_board[board] = [
            player
            for player in previous
            if isinstance(player, int) and player not in playing
        ]
        if not available_by_board[board]:
            return None

    board_order = sorted(
        boards,
        key=lambda board: (len(available_by_board[board]), rng.random()),
    )
    referee_to_board = {}

    def assign_referee(board, seen):
        candidates = sorted(
            available_by_board[board],
            key=lambda player: (referee_counts[player], rng.random()),
        )
        for referee in candidates:
            if referee in seen:
                continue
            seen.add(referee)
            previous_board = referee_to_board.get(referee)
            if previous_board is None or assign_referee(previous_board, seen):
                referee_to_board[referee] = board
                return True
        return False

    for board in board_order:
        if not assign_referee(board, set()):
            return None
    board_to_referee = {
        board: referee for referee, board in referee_to_board.items()
    }
    shuffled_games = rng.sample(games, len(games))
    return {
        board: (game, board_to_referee[board])
        for board, game in zip(boards, shuffled_games)
    }


def _pick_wave(
    edges,
    board_count,
    previous_games,
    referee_counts,
    rng,
    appearance_counts=None,
    player_pool=None,
    last_played_round=None,
    current_round=1,
    consecutive_matches=None,
):
    target = min(board_count, len(edges))
    if target == 0:
        return []

    def progress_penalty(game):
        return sum(
            max(
                0,
                player_round - (appearance_counts or {}).get(player, 0) - 1,
            )
            for player, player_round in getattr(game, "player_rounds", {}).items()
        )

    def wait_priority(game):
        waits = [
            current_round - (last_played_round or {}).get(player, 0)
            for player in game
            if isinstance(player, int)
        ]
        return -max(waits, default=0), -sum(waits)

    def consecutive_priority(game):
        return sum(
            (consecutive_matches or {}).get(player, 0) > 0
            for player in game
            if isinstance(player, int)
        )

    target_wait = max(
        2,
        (len(player_pool) + 2 * board_count - 1) // (2 * board_count)
        if player_pool is not None else 2,
    )

    def overdue_priority(game):
        return -max(
            (
                max(0, current_round - (last_played_round or {}).get(player, 0) - target_wait)
                for player in game if isinstance(player, int)
            ),
            default=0,
        )

    previous_players = {
        player
        for game in previous_games
        for player in game
        if isinstance(player, int)
    }
    attempts = 20 if len(edges) > 100 else 50
    for penalty_limit in sorted({progress_penalty(game) for game in edges}):
        eligible_edges = [
            game for game in edges if progress_penalty(game) <= penalty_limit
        ]
        if len(eligible_edges) < target:
            continue
        for _ in range(attempts):
            candidates = sorted(
                eligible_edges,
                key=lambda game: (
                    overdue_priority(game),
                    consecutive_priority(game),
                    *wait_priority(game),
                    len(set(game) & previous_players),
                    progress_penalty(game),
                    sum(getattr(game, "player_rounds", {}).values()),
                    max(
                        (appearance_counts or {}).get(player, 0)
                        for player in game
                        if isinstance(player, int)
                    ),
                    sum(
                        (appearance_counts or {}).get(player, 0)
                        for player in game
                        if isinstance(player, int)
                    ),
                    rng.random(),
                ),
            )
            selected = []
            playing = set()
            for game in candidates:
                participants = {player for player in game if isinstance(player, int)}
                if participants & playing:
                    continue
                selected.append(game)
                playing.update(participants)
                if len(selected) == target:
                    board_sets = (
                        [tuple(range(board_count))]
                        if target == board_count
                        else list(combinations(range(board_count), target))
                    )
                    rng.shuffle(board_sets)
                    for boards in board_sets:
                        assignment = _assign_wave(
                            list(boards),
                            selected,
                            previous_games,
                            playing,
                            referee_counts,
                            rng,
                        )
                        if assignment is not None:
                            return [
                                (board, *assignment[board])
                                for board in boards
                            ]

    all_players = tuple(
        player_pool
        if player_pool is not None
        else sorted(
            {
                player
                for game in edges
                for player in game
                if isinstance(player, int)
            }
        )
    )
    fallback_previous_games = [all_players] * board_count
    for _ in range(attempts):
        candidates = sorted(
            edges,
            key=lambda game: (
                overdue_priority(game),
                consecutive_priority(game),
                *wait_priority(game),
                progress_penalty(game),
                rng.random(),
            ),
        )
        selected = []
        playing = set()
        for game in candidates:
            participants = {player for player in game if isinstance(player, int)}
            if participants & playing:
                continue
            selected.append(game)
            playing.update(participants)
            if len(selected) == target:
                board_sets = (
                    [tuple(range(board_count))]
                    if target == board_count
                    else list(combinations(range(board_count), target))
                )
                rng.shuffle(board_sets)
                for boards in board_sets:
                    assignment = _assign_wave(
                        list(boards),
                        selected,
                        fallback_previous_games,
                        playing,
                        referee_counts,
                        rng,
                    )
                    if assignment is not None:
                        for game in selected:
                            game.referee_fallback = True
                        return [
                            (board, *assignment[board])
                            for board in boards
                        ]

    if target == board_count:
        raise ScheduleError("Er kon geen volledig gevulde ronde met beschikbare scheidsrechters worden gemaakt.")
    raise ScheduleError("Er kon geen geldige laatste ronde met scheidsrechters worden gemaakt.")


def _generate_schedule_once(
    player_count,
    requested_board_count,
    match_count,
    seed,
    unmatched_player=0,
):
    rng = random.Random(seed)
    all_pairs = _pairings(player_count, match_count, unmatched_player)
    stroman_pairs = [pair for pair in all_pairs if "stroman" in pair]
    real_pairs = [pair for pair in all_pairs if "stroman" not in pair]

    board_count = min(
        requested_board_count,
        max(1, player_count // 3),
        max(1, len(all_pairs) // 2),
    )
    if len(real_pairs) < board_count * 2:
        board_count = max(1, len(real_pairs) // 2)
    if board_count <= 0:
        raise ScheduleError("Er zijn onvoldoende wedstrijden om scheidsrechters op elk bord te laten rouleren.")

    # Reserve a final full round to seed first-round referees. The bye match
    # joins the final partial wave when that leaves an unused board.
    final_factor = [
        game
        for game in real_pairs
        if all(
            player_round == match_count
            for player_round in game.player_rounds.values()
        )
    ]
    if len(final_factor) < board_count:
        raise ScheduleError("Er zijn onvoldoende wedstrijden in de laatste spelersronde.")
    final_round = rng.sample(final_factor, board_count)
    rng.shuffle(real_pairs)
    reserved_games = Counter(final_round)
    remaining = []
    for game in real_pairs:
        if reserved_games[game]:
            reserved_games[game] -= 1
        else:
            remaining.append(game)
    previous_games = list(final_round)
    referee_counts = Counter()
    appearance_counts = Counter()
    matches = []
    round_number = 1
    last_partial_boards = set()

    while len(remaining) >= board_count:
        wave = _pick_wave(
            remaining,
            board_count,
            previous_games,
            referee_counts,
            rng,
            appearance_counts,
        )
        current_games = [None] * board_count
        for board, game, referee in wave:
            current_games[board] = game
            matches.append({
                "number": len(matches) + 1,
                "round": round_number,
                "board": board + 1,
                "player1": game[0],
                "player2": game[1],
                "referee": referee,
                "player_rounds": game.player_rounds.copy(),
            })
            referee_counts[referee] += 1
            appearance_counts.update(player for player in game if isinstance(player, int))
            remaining.remove(game)
        for board, game in enumerate(current_games):
            if game is not None:
                previous_games[board] = game
        round_number += 1

    final_candidates = [*final_round, *remaining]
    final_wave = _pick_wave(
        final_candidates,
        board_count,
        previous_games,
        referee_counts,
        rng,
        appearance_counts,
    )
    final_games = Counter(game for _, game, _ in final_wave)
    remaining = []
    for game in final_candidates:
        if final_games[game]:
            final_games[game] -= 1
        else:
            remaining.append(game)
    final_wave = {
        board: (game, referee)
        for board, game, referee in final_wave
    }
    for board in range(board_count):
        game, referee = final_wave[board]
        matches.append({
            "number": len(matches) + 1,
            "round": round_number,
            "board": board + 1,
            "player1": game[0],
            "player2": game[1],
            "referee": referee,
            "player_rounds": game.player_rounds.copy(),
        })
        referee_counts[referee] += 1
        appearance_counts.update(player for player in game if isinstance(player, int))
        previous_games[board] = game
    round_number += 1

    if remaining:
        wave = _pick_wave(
            remaining,
            board_count,
            previous_games,
            referee_counts,
            rng,
            appearance_counts,
        )
        last_partial_boards = {board for board, _, _ in wave}
        for board, game, referee in wave:
            matches.append({
                "number": len(matches) + 1,
                "round": round_number,
                "board": board + 1,
                "player1": game[0],
                "player2": game[1],
                "referee": referee,
                "player_rounds": game.player_rounds.copy(),
            })
            referee_counts[referee] += 1
            appearance_counts.update(player for player in game if isinstance(player, int))
            previous_games[board] = game
            remaining.remove(game)
        round_number += 1

    while stroman_pairs:
        current_round = round_number - 1 if last_partial_boards else round_number
        matches_in_round = [
            match for match in matches if match["round"] == current_round
        ]
        playing = {
            player
            for match in matches_in_round
            for player in (match["player1"], match["player2"])
            if isinstance(player, int)
        }
        refs_in_round = {match["referee"] for match in matches_in_round}
        empty_boards = (
            [board for board in range(board_count) if board not in last_partial_boards]
            if last_partial_boards
            else list(range(board_count))
        )
        options = [
            (referee_counts[referee], board, game, referee)
            for board in empty_boards
            for game in stroman_pairs
            for referee in previous_games[board]
            if isinstance(referee, int)
            and referee != game[0]
            and game[0] not in playing
            and referee not in playing
            and referee not in refs_in_round
        ]
        if not options:
            if last_partial_boards:
                last_partial_boards = set()
                continue
            raise ScheduleError("Er kon geen scheidsrechter voor de stromanwedstrijd worden gevonden.")
        _, board, game, referee = min(options)
        matches.append({
            "number": len(matches) + 1,
            "round": current_round,
            "board": board + 1,
            "player1": game[0],
            "player2": game[1],
            "referee": referee,
            "player_rounds": game.player_rounds.copy(),
        })
        referee_counts[referee] += 1
        appearance_counts.update(player for player in game if isinstance(player, int))
        previous_games[board] = game
        stroman_pairs.remove(game)
        if current_round == round_number:
            round_number += 1

    players_by_round = {}
    for match in matches:
        playing = players_by_round.setdefault(match["round"], set())
        participants = [
            player
            for player in (match["player1"], match["player2"])
            if isinstance(player, int)
        ]
        if playing.intersection(participants):
            raise ScheduleError("Een speler kan maar één wedstrijd per ronde spelen.")
        playing.update(participants)
    return matches


def _generate_progressive_schedule_once(
    player_count,
    requested_board_count,
    match_count,
    seed,
    unmatched_player=0,
):
    rng = random.Random(seed)
    remaining = _pairings(player_count, match_count, unmatched_player, seed=seed)
    board_count = min(
        requested_board_count,
        max(1, player_count // 3),
        max(1, len(remaining) // 2),
    )
    if board_count <= 0:
        raise ScheduleError("Er zijn onvoldoende wedstrijden om scheidsrechters op elk bord te laten rouleren.")

    previous_games = [tuple(range(player_count))] * board_count
    referee_counts = Counter()
    appearance_counts = Counter()
    last_played_round = Counter()
    consecutive_matches = Counter()
    matches = []
    round_number = 1

    while remaining:
        ready_games = []
        for game in remaining:
            if "stroman" in game:
                unmatched_player = game.player_rounds[game[0]]
                is_ready = (
                    appearance_counts[game[0]] == unmatched_player - 1
                    and all(
                        appearance_counts[player] >= match_count
                        for player in range(player_count)
                        if player != game[0]
                    )
                )
            else:
                is_ready = all(
                    player_round
                    <= appearance_counts[player] + 1
                    for player, player_round in game.player_rounds.items()
                )
            if is_ready:
                ready_games.append(game)
        if not ready_games:
            raise ScheduleError("Er is geen wedstrijd beschikbaar op de volgende spelersronde.")

        rested_games = [
            game for game in ready_games
            if all(
                consecutive_matches[player] < 2
                for player in game if isinstance(player, int)
            )
        ]
        if not rested_games:
            consecutive_matches.clear()
            round_number += 1
            continue
        for wave_size in range(board_count, 0, -1):
            try:
                wave = _pick_wave(
                    rested_games,
                    wave_size,
                    previous_games,
                    referee_counts,
                    rng,
                    appearance_counts,
                    range(player_count),
                    last_played_round,
                    round_number,
                    consecutive_matches,
                )
            except ScheduleError:
                if wave_size == 1:
                    raise
            else:
                break
        playing_in_wave = {
            player for _, game, _ in wave
            for player in game if isinstance(player, int)
        }
        for player in range(player_count):
            consecutive_matches[player] = (
                consecutive_matches[player] + 1 if player in playing_in_wave else 0
            )
        for board, game, referee in wave:
            match = {
                "number": len(matches) + 1,
                "round": round_number,
                "board": board + 1,
                "player1": game[0],
                "player2": game[1],
                "referee": referee,
                "player_rounds": game.player_rounds.copy(),
                "referee_fallback": getattr(game, "referee_fallback", False),
            }
            matches.append(match)
            referee_counts[referee] += 1
            appearance_counts.update(
                player for player in game if isinstance(player, int)
            )
            for player in game:
                if isinstance(player, int):
                    last_played_round[player] = round_number
            remaining.remove(game)
            previous_games[board] = game
        round_number += 1

    return matches


def _rebalance_referees(matches, player_count, allow_fallback=False):
    matches_by_round = {}
    for match in matches:
        matches_by_round.setdefault(match["round"], []).append(match)
    board_count = max(match["board"] for match in matches)
    if allow_fallback:
        previous_games = {board: () for board in range(1, board_count + 1)}
    else:
        seed_round = max(
            round_number
            for round_number, round_matches in matches_by_round.items()
            if len(round_matches) == board_count
        )
        previous_games = {
            match["board"]: (match["player1"], match["player2"])
            for match in matches_by_round[seed_round]
        }
    round_choices = []
    for round_number in sorted(matches_by_round):
        round_matches = matches_by_round[round_number]
        playing = {
            player
            for match in round_matches
            for player in (match["player1"], match["player2"])
            if isinstance(player, int)
        }
        choices = {}
        for match in round_matches:
            previous = previous_games[match["board"]]
            choices[match["board"]] = [
                player
                for player in previous
                if isinstance(player, int) and player not in playing
            ]
            if allow_fallback:
                choices[match["board"]].extend(
                    player for player in range(player_count)
                    if player not in playing and player not in previous
                )
        round_choices.append((round_number, round_matches, choices))
        for match in round_matches:
            previous_games[match["board"]] = (
                match["player1"],
                match["player2"],
            )

    graph = []

    def add_node():
        graph.append([])
        return len(graph) - 1

    def add_edge(start, end, capacity, cost):
        forward = [end, len(graph[end]), capacity, cost]
        reverse = [start, len(graph[start]), 0, -cost]
        graph[start].append(forward)
        graph[end].append(reverse)
        return forward

    source = add_node()
    sink = add_node()
    player_nodes = {player: add_node() for player in range(player_count)}
    rounds_by_player = {}
    board_edges = {}
    required_flow = 0
    for round_number, round_matches, choices in round_choices:
        round_players = {
            player: add_node()
            for player in {
                player
                for board_choices in choices.values()
                for player in board_choices
            }
        }
        for player, node in round_players.items():
            add_edge(node, player_nodes[player], 1, 0)
            rounds_by_player.setdefault(player, set()).add(round_number)
        for match in round_matches:
            board_node = add_node()
            add_edge(source, board_node, 1, 0)
            for player in choices[match["board"]]:
                board_edges[(round_number, match["board"], player)] = add_edge(
                    board_node,
                    round_players[player],
                    1,
                    0,
                )
            required_flow += 1

    for player, rounds in rounds_by_player.items():
        for duty_number in range(1, len(rounds) + 1):
            add_edge(player_nodes[player], sink, 1, 2 * duty_number - 1)

    flow = 0
    potentials = [0] * len(graph)
    while flow < required_flow:
        distances = [float("inf")] * len(graph)
        previous = [None] * len(graph)
        distances[source] = 0
        queue = [(0, source)]
        while queue:
            distance, start = heapq.heappop(queue)
            if distance != distances[start]:
                continue
            for edge_index, edge in enumerate(graph[start]):
                end, _, capacity, cost = edge
                if not capacity:
                    continue
                reduced_cost = cost + potentials[start] - potentials[end]
                next_distance = distance + reduced_cost
                if next_distance < distances[end]:
                    distances[end] = next_distance
                    previous[end] = (start, edge_index)
                    heapq.heappush(queue, (next_distance, end))
        if previous[sink] is None:
            return matches
        for node, distance in enumerate(distances):
            if distance < float("inf"):
                potentials[node] += distance
        node = sink
        while node != source:
            start, edge_index = previous[node]
            edge = graph[start][edge_index]
            edge[2] -= 1
            graph[node][edge[1]][2] += 1
            node = start
        flow += 1

    for round_number, round_matches, _ in round_choices:
        for match in round_matches:
            for player in range(player_count):
                edge = board_edges.get((round_number, match["board"], player))
                if edge is not None and edge[2] == 0:
                    match["referee"] = player
                    break
    return matches


def _schedule_respects_board_rules(matches, player_count, board_count):
    if not matches:
        return False
    rounds = {}
    duties = Counter()
    previous_players = {}
    for match in sorted(matches, key=lambda item: (item["round"], item["board"])):
        block_round = match["round"]
        board = match["board"]
        referee = match["referee"]
        if not 1 <= board <= board_count or referee not in range(player_count):
            return False
        games = rounds.setdefault(block_round, [])
        if any(game["board"] == board for game in games):
            return False
        participants = {match["player1"], match["player2"]}
        if referee in participants:
            return False
        if board in previous_players and referee not in previous_players[board]:
            return False
        games.append(match)
        previous_players[board] = participants
        duties[referee] += 1
    expected_rounds = (len(matches) + board_count - 1) // board_count
    if set(rounds) != set(range(1, expected_rounds + 1)):
        return False
    for block_round, games in rounds.items():
        expected = (
            board_count if block_round < expected_rounds
            else len(matches) - board_count * (expected_rounds - 1)
        )
        if len(games) != expected:
            return False
        players = [player for game in games for player in (game["player1"], game["player2"])]
        referees = [game["referee"] for game in games]
        if (
            len(players) != len(set(players))
            or len(referees) != len(set(referees))
            or set(players) & set(referees)
        ):
            return False
    counts = [duties[player] for player in range(player_count)]
    return max(counts) - min(counts) <= 1


def _assign_strict_board_schedule(matches, player_count, board_count, group_phases=True):
    model = cp_model.CpModel()
    game_count = len(matches)
    round_count = (game_count + board_count - 1) // board_count
    phases = {}
    for index, match in enumerate(matches):
        phase = min(match["player_rounds"].values()) if group_phases else 0
        phases.setdefault(phase, []).append(index)
    positions = [None] * game_count
    games_at_slot = [None] * game_count
    hints = {}
    offset = 0
    for phase in sorted(phases):
        indices = phases[phase]
        for rank, index in enumerate(indices):
            positions[index] = model.new_int_var(offset, offset + len(indices) - 1, f"position_{index}")
            hints[index] = offset + rank
            games_at_slot[offset + rank] = model.new_int_var_from_domain(
                cp_model.Domain.from_values(indices), f"game_{offset + rank}"
            )
        offset += len(indices)
    model.add_inverse(positions, games_at_slot)
    times = [model.new_int_var(0, round_count - 1, f"time_{index}") for index in range(game_count)]
    times_by_player = [[] for _ in range(player_count)]
    for index, match in enumerate(matches):
        model.add_division_equality(times[index], positions[index], board_count)
        model.add_hint(positions[index], hints[index])
        for player in (match["player1"], match["player2"]):
            times_by_player[player].append(times[index])
        if match.get("stroman_player") is not None:
            model.add(positions[index] == game_count - 1)
    first_players = [model.new_int_var(0, player_count - 1, f"first_{slot}") for slot in range(game_count)]
    second_players = [model.new_int_var(0, player_count - 1, f"second_{slot}") for slot in range(game_count)]
    referees = [model.new_int_var(0, player_count - 1, f"referee_{slot}") for slot in range(game_count)]
    for slot in range(game_count):
        model.add_element(games_at_slot[slot], [match["player1"] for match in matches], first_players[slot])
        model.add_element(games_at_slot[slot], [match["player2"] for match in matches], second_players[slot])
        if slot >= board_count:
            model.add_allowed_assignments(
                [games_at_slot[slot - board_count], referees[slot]],
                [(index, player) for index, match in enumerate(matches)
                 for player in (match["player1"], match["player2"])],
            )
    last_round_size = game_count % board_count or board_count
    for first in range(last_round_size - 1):
        model.add(games_at_slot[first] < games_at_slot[first + 1])
    for first in range(last_round_size, board_count - 1):
        model.add(games_at_slot[first] < games_at_slot[first + 1])
    for start in range(0, game_count, board_count):
        end = min(game_count, start + board_count)
        model.add_all_different(first_players[start:end] + second_players[start:end] + referees[start:end])
    for player in range(player_count):
        assignments = []
        for slot, referee in enumerate(referees):
            assigned = model.new_bool_var(f"duty_{player}_{slot}")
            model.add(referee == player).only_enforce_if(assigned)
            model.add(referee != player).only_enforce_if(assigned.negated())
            assignments.append(assigned)
        model.add(sum(assignments) >= game_count // player_count)
        model.add(sum(assignments) <= (game_count + player_count - 1) // player_count)
    maxima = []
    doubles = []
    for player, player_times in enumerate(times_by_player):
        gaps = [player_times[0], round_count - player_times[-1] - 1]
        for index, (left, right) in enumerate(zip(player_times, player_times[1:])):
            model.add(right > left)
            gaps.append(right - left - 1)
            double = model.new_bool_var(f"consecutive_{player}_{index}")
            model.add(right == left + 1).only_enforce_if(double)
            model.add(right != left + 1).only_enforce_if(double.negated())
            doubles.append(double)
        for first, third in zip(player_times, player_times[2:]):
            model.add(third >= first + 3)
        maximum = model.new_int_var(0, round_count, f"rest_{player}")
        model.add_max_equality(maximum, gaps)
        maxima.append(maximum)
    if player_count >= 5 * board_count:
        model.add(sum(doubles) == 0)
    maximum_rest = model.new_int_var(0, round_count, "maximum_rest")
    model.minimize(sum(doubles))
    model.add_max_equality(maximum_rest, maxima)
    feasible_solver = cp_model.CpSolver()
    feasible_solver.parameters.max_time_in_seconds = 15
    feasible_solver.parameters.num_search_workers = 8
    feasible_solver.parameters.stop_after_first_solution = True
    status = feasible_solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        if group_phases:
            return _assign_strict_board_schedule(matches, player_count, board_count, group_phases=False)
        return None
    model.clear_hints()
    for variable in positions + games_at_slot + referees:
        model.add_hint(variable, feasible_solver.value(variable))
    solver = _solve_rest_limits(
        model, maximum_rest, feasible_solver.value(maximum_rest),
        workers=8, deterministic_budget=2, time_budget=8,
    )
    if solver is None:
        solver = feasible_solver
    result = []
    for slot in range(game_count):
        result.append({
            **matches[solver.value(games_at_slot[slot])],
            "number": slot + 1,
            "round": slot // board_count + 1,
            "board": slot % board_count + 1,
            "referee": solver.value(referees[slot]),
            "referee_fallback": False,
        })
    if not _schedule_respects_board_rules(result, player_count, board_count):
        return None
    return result


def _rest_swap_score(matches, player_count):
    rounds_by_player = [[] for _ in range(player_count)]
    round_players = {}
    doubles = 0
    for match in matches:
        block_round = match["round"]
        playing = round_players.setdefault(block_round, set())
        participants = {match["player1"], match["player2"]}
        if participants & playing:
            return None
        playing.update(participants)
        for player in participants:
            player_rounds = rounds_by_player[player]
            if match["player_rounds"][player] != len(player_rounds) + 1:
                return None
            if player_rounds and player_rounds[-1] == block_round - 1:
                doubles += 1
                if len(player_rounds) > 1 and player_rounds[-2] == block_round - 2:
                    return None
            player_rounds.append(block_round)
    last_round = matches[-1]["round"]
    rest_maxima = [
        max(
            rounds[0] - 1,
            last_round - rounds[-1],
            max((right - left - 1 for left, right in zip(rounds, rounds[1:])), default=0),
        )
        for rounds in rounds_by_player
    ]
    return (
        max(rest_maxima),
        max(rest_maxima) - min(rest_maxima),
        sum(rest * rest for rest in rest_maxima),
        doubles,
    )


def _solve_rest_limits(
    model, maximum_rest, upper_bound,
    workers=1, deterministic_budget=0.3, time_budget=3,
):
    for rest_limit in range(1, upper_bound + 1):
        limit_assumption = model.new_bool_var(f"rest_limit_{rest_limit}")
        model.add(maximum_rest <= rest_limit).only_enforce_if(limit_assumption)
        model.clear_assumptions()
        model.add_assumption(limit_assumption)
        solver = cp_model.CpSolver()
        solver.parameters.max_deterministic_time = deterministic_budget
        solver.parameters.max_time_in_seconds = time_budget
        solver.parameters.num_search_workers = workers
        status = solver.solve(model)
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return solver
        if status == cp_model.UNKNOWN:
            logger.info("Rustgrens %s onbeslist binnen de zoeklimiet.", rest_limit)
        elif status != cp_model.INFEASIBLE:
            logger.warning("Rustoptimalisatie afgebroken: %s", solver.status_name(status))
            return None
    return None


def _improve_rest_distribution(matches, player_count):
    board_count = max(match["board"] for match in matches)
    if _schedule_respects_board_rules(matches, player_count, board_count):
        rounds_by_player = [[] for _ in range(player_count)]
        for match in matches:
            for player in (match["player1"], match["player2"]):
                rounds_by_player[player].append(match["round"])
        has_triple = any(
            third == second + 1 and second == first + 1
            for rounds in rounds_by_player
            for first, second, third in zip(rounds, rounds[1:], rounds[2:])
        )
        has_double = any(
            right == left + 1
            for rounds in rounds_by_player
            for left, right in zip(rounds, rounds[1:])
        )
        if not has_triple and (player_count < 5 * board_count or not has_double):
            return matches
    result = _assign_strict_board_schedule(
        matches, player_count, board_count
    )
    if result is None:
        raise ScheduleError(
            "Geen geldig schema gevonden met volle blokrondes, vaste scheidsrechterrotatie "
            "en gelijk verdeelde scheidsrechterbeurten. Probeer minder dartsblokken, "
            "wijzig het aantal spelers of pas het aantal wedstrijden per speler aan."
        )
    return result


def generate_schedule(player_count, board_count, match_count=5, stroman_player=None):
    if not 4 <= player_count <= 128:
        raise ScheduleError("Een competitieavond moet 4 tot en met 128 spelers hebben.")
    if not 2 <= board_count <= 30:
        raise ScheduleError("Kies 2 tot en met 30 dartsblokken.")
    if not 1 <= match_count <= 20:
        raise ScheduleError("Kies 1 tot en met 20 wedstrijden per speler.")
    if stroman_player is not None and not 0 <= stroman_player < player_count:
        raise ScheduleError("De gekozen stroman moet een aanwezige speler zijn.")

    best_schedule = None
    best_score = None
    attempts = 48 if player_count <= 30 else 1
    seed_offset = 0 if player_count <= 30 else 43
    for attempt in range(attempts):
        unmatched_player = (
            attempt % player_count
            if stroman_player is None
            else (stroman_player + 1 + attempt % (player_count - 1)) % player_count
        )
        try:
            schedule = _generate_progressive_schedule_once(
                player_count,
                board_count,
                match_count,
                unmatched_player=unmatched_player,
                seed=(
                    player_count * 1009 + board_count * 9176 + match_count * 3571 + attempt * 7919
                    if player_count <= 30
                    else seed_offset
                ),
            )
        except ScheduleError:
            continue

        stroman_match = next(
            (
                match
                for match in schedule
                if "stroman" in (match["player1"], match["player2"])
            ),
            None,
        )
        selected_stroman = stroman_player
        stroman_repeat_count = 0
        if stroman_match:
            unmatched_player = stroman_match["player1"]
            matches_in_round = [
                match
                for match in schedule
                if match["round"] == stroman_match["round"]
                and match is not stroman_match
            ]
            playing_in_round = {
                player
                for match in matches_in_round
                for player in (match["player1"], match["player2"])
                if isinstance(player, int)
            }
            referees_in_round = {
                match["referee"] for match in matches_in_round
            }
            referees_in_round.add(stroman_match["referee"])
            previous_round_players = {
                player
                for match in schedule[:-1]
                if match["round"] == stroman_match["round"] - 1
                for player in (match["player1"], match["player2"])
                if isinstance(player, int)
            }
            earlier_round_players = {
                player
                for match in schedule[:-1]
                if match["round"] == stroman_match["round"] - 2
                for player in (match["player1"], match["player2"])
                if isinstance(player, int)
            }
            available_stromans = {
                player
                for match in schedule[:-1]
                for player in (match["player1"], match["player2"])
                if isinstance(player, int)
                and player != unmatched_player
                and player not in playing_in_round
                and player not in referees_in_round
                and player not in previous_round_players & earlier_round_players
            }
            if selected_stroman is None:
                if not available_stromans:
                    continue
                earlier_opponents = Counter(
                    player
                    for match in schedule[:-1]
                    if unmatched_player in (match["player1"], match["player2"])
                    for player in (match["player1"], match["player2"])
                    if isinstance(player, int) and player != unmatched_player
                )
                minimum_encounters = min(
                    earlier_opponents[player] for player in available_stromans
                )
                available_stromans = {
                    player for player in available_stromans
                    if earlier_opponents[player] == minimum_encounters
                }
                selected_stroman = random.SystemRandom().choice(
                    sorted(available_stromans - previous_round_players or available_stromans)
                )
                stroman_repeat_count = earlier_opponents[selected_stroman]
            elif selected_stroman not in available_stromans:
                continue
            stroman_match["player2"] = selected_stroman
            stroman_match["stroman_player"] = selected_stroman
            stroman_match["player_rounds"][selected_stroman] = (
                stroman_match["player_rounds"].pop("stroman")
            )

        appearances = Counter(
            player
            for match in schedule
            for player in (match["player1"], match["player2"])
            if isinstance(player, int) and player != match.get("stroman_player")
        )
        expected_stroman_matches = int(
            player_count % 2 == 1 and match_count % 2 == 1
        )
        stroman_matches = [
            match
            for match in schedule
            if match.get("stroman_player") is not None
        ]
        stroman_is_last = (
            not stroman_matches or schedule[-1] == stroman_matches[0]
        )
        if (
            len(schedule) != expected_match_count(player_count, match_count)
            or set(appearances) != set(range(player_count))
            or set(appearances.values()) != {match_count}
            or len(stroman_matches) != expected_stroman_matches
            or not stroman_is_last
            or stroman_matches
            and stroman_player is not None
            and stroman_matches[0]["stroman_player"] != stroman_player
        ):
            continue
        players_by_round = {}
        rounds_valid = True
        for match in schedule:
            participants = {
                player
                for player in (match["player1"], match["player2"])
                if isinstance(player, int)
            }
            round_players = players_by_round.setdefault(match["round"], set())
            if round_players & participants:
                rounds_valid = False
                break
            round_players.update(participants)
        if not rounds_valid:
            continue
        chronological_rounds = Counter()
        for match in sorted(
            schedule,
            key=lambda item: (item["round"], item["number"]),
        ):
            if any(
                match["player_rounds"].get(player)
                != chronological_rounds[player] + 1
                for player in (match["player1"], match["player2"])
                if isinstance(player, int)
            ):
                rounds_valid = False
                break
            chronological_rounds.update(
                player
                for player in (match["player1"], match["player2"])
                if isinstance(player, int)
            )
        if not rounds_valid:
            continue
        regular_matches = [
            match
            for match in schedule
            if isinstance(match["player2"], int)
            and match.get("stroman_player") is None
        ]
        rounds = {}
        for match in regular_matches:
            rounds.setdefault(match["round"], []).append(match)
        referee_counts = Counter(match["referee"] for match in schedule)
        duties = [referee_counts.get(player, 0) for player in range(player_count)]
        first_rounds = {
            player: min(
                match["round"]
                for match in schedule
                if player in (match["player1"], match["player2"])
            )
            for player in range(player_count)
        }
        block_rounds_by_player = {player: [] for player in range(player_count)}
        for match in schedule:
            for player in (match["player1"], match["player2"]):
                if isinstance(player, int):
                    block_rounds_by_player[player].append(match["round"])
        empty_round_gaps = [
            right - left - 1
            for block_rounds in block_rounds_by_player.values()
            for left, right in zip(block_rounds, block_rounds[1:])
        ]
        consecutive_pairs = sum(gap == 0 for gap in empty_round_gaps)
        last_block_round = max(match["round"] for match in schedule)
        maximum_rest_by_player = [
            max(
                block_rounds[0] - 1,
                last_block_round - block_rounds[-1],
                max(
                    (right - left - 1 for left, right in zip(block_rounds, block_rounds[1:])),
                    default=0,
                ),
            )
            for block_rounds in block_rounds_by_player.values()
        ]
        if any(
            third == second + 1 and second == first + 1
            for block_rounds in block_rounds_by_player.values()
            for first, second, third in zip(
                block_rounds, block_rounds[1:], block_rounds[2:]
            )
        ):
            continue
        partial_rounds = sum(len(matches) < min(board_count, player_count // 3) for matches in rounds.values())
        score = (
            max(duties) - min(duties),
            consecutive_pairs,
            max(maximum_rest_by_player),
            max(maximum_rest_by_player) - min(maximum_rest_by_player),
            sum(rest * rest for rest in maximum_rest_by_player),
            max(0, partial_rounds - int(len(regular_matches) % min(board_count, player_count // 3) != 0)),
            sum(min(board_count, player_count // 3) - len(matches) for matches in rounds.values() if len(matches) < min(board_count, player_count // 3)),
            max(first_rounds.values()),
            sum(first_rounds.values()),
            sum(count * count for count in duties),
            max(empty_round_gaps, default=0),
            sum(empty_round_gaps),
        )
        ranking_score = (stroman_repeat_count, *score)
        if best_score is None or ranking_score < best_score:
            best_schedule, best_score = schedule, ranking_score
            expected_spread = 1 if len(schedule) >= player_count else 0
            target_empty_gap = max(
                0,
                (player_count + 2 * min(board_count, player_count // 3) - 1)
                // (2 * min(board_count, player_count // 3))
                - 1,
            )
            if (
                stroman_repeat_count == 0
                and consecutive_pairs == 0
                and score[5] == 0
                and score[0] <= expected_spread
                and score[2] <= target_empty_gap
                and score[3] <= 1
            ):
                break

    if best_schedule is None:
        if stroman_player is not None and player_count % 2 and match_count % 2:
            raise StromanSelectionError(
                "De gekozen speler kan in dit schema niet als stroman worden geloot. "
                "Kies een andere speler."
            )
        raise ScheduleError("Er kon geen geldig schema met een evenwichtige scheidsrechterverdeling worden gemaakt.")
    return _improve_rest_distribution(best_schedule, player_count)
