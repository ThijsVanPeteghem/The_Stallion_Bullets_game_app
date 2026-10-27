from collections import Counter
import heapq
import random
from itertools import combinations


class ScheduleError(ValueError):
    pass


def _pairings(player_count, match_count=5):
    if player_count % 2:
        edges = []
        for offset in range(1, match_count // 2 + 1):
            offset %= player_count
            if offset == 0:
                offset = 1
            for player in range(player_count):
                edges.append(
                    tuple(sorted((player, (player + offset) % player_count)))
                )

        if match_count % 2:
            half = (player_count - 1) // 2
            edges.extend(
                (player, player + half)
                for player in range(1, half + 1)
            )
            edges.append((0, "stroman"))
        return edges

    participant_count = player_count + player_count % 2
    circle = list(range(participant_count))
    round_count = participant_count - 1
    factors = []

    for _ in range(round_count):
        games = []
        for index in range(participant_count // 2):
            left = circle[index]
            right = circle[participant_count - 1 - index]
            games.append(tuple(sorted((left, right))))
        factors.append(games)
        circle = [circle[0], circle[-1], *circle[1:-1]]

    return [
        game
        for round_number in range(match_count)
        for game in factors[round_number % round_count]
    ]


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
):
    target = min(board_count, len(edges))
    if target == 0:
        return []

    previous_players = {
        player
        for game in previous_games
        for player in game
        if isinstance(player, int)
    }
    attempts = 20 if len(edges) > 100 else 50
    for _ in range(attempts):
        candidates = sorted(
            edges,
            key=lambda game: (
                len(set(game) & previous_players),
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

    if target == board_count:
        raise ScheduleError("Er kon geen volledig gevulde ronde met beschikbare scheidsrechters worden gemaakt.")
    raise ScheduleError("Er kon geen geldige laatste ronde met scheidsrechters worden gemaakt.")


def _generate_schedule_once(player_count, requested_board_count, match_count, seed):
    rng = random.Random(seed)
    all_pairs = _pairings(player_count, match_count)
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
    if player_count % 2 == 0:
        factor_size = player_count // 2
        factors = [
            real_pairs[index:index + factor_size]
            for index in range(0, len(real_pairs), factor_size)
        ]
        factor = rng.choice(factors)
        final_round = rng.sample(factor, board_count)
    else:
        final_round = _select_disjoint_games(real_pairs, board_count, rng)
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
            })
            referee_counts[referee] += 1
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
        })
        referee_counts[referee] += 1
        previous_games[board] = game
    round_number += 1

    if remaining:
        wave = _pick_wave(
            remaining,
            board_count,
            previous_games,
            referee_counts,
            rng,
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
            })
            referee_counts[referee] += 1
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
        })
        referee_counts[referee] += 1
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


def _rebalance_referees(matches, player_count):
    matches_by_round = {}
    for match in matches:
        matches_by_round.setdefault(match["round"], []).append(match)
    board_count = max(match["board"] for match in matches)
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


def generate_schedule(player_count, board_count, match_count=5):
    if not 4 <= player_count <= 128:
        raise ScheduleError("Een competitieavond moet 4 tot en met 128 spelers hebben.")
    if not 2 <= board_count <= 30:
        raise ScheduleError("Kies 2 tot en met 30 dartsblokken.")
    if not 1 <= match_count <= 20:
        raise ScheduleError("Kies 1 tot en met 20 wedstrijden per speler.")

    best_schedule = None
    best_score = None
    attempts = 48 if player_count <= 30 else 1
    seed_offset = 0 if player_count <= 30 else 43
    for attempt in range(attempts):
        try:
            schedule = _generate_schedule_once(
                player_count,
                board_count,
                match_count,
                seed=(
                    player_count * 1009 + board_count * 9176 + match_count * 3571 + attempt * 7919
                    if player_count <= 30
                    else seed_offset
                ),
            )
        except ScheduleError:
            continue

        schedule = _rebalance_referees(schedule, player_count)
        regular_matches = [match for match in schedule if isinstance(match["player2"], int)]
        rounds = {}
        for match in regular_matches:
            rounds.setdefault(match["round"], []).append(match)
        referee_counts = Counter(match["referee"] for match in schedule)
        duties = [referee_counts.get(player, 0) for player in range(player_count)]
        partial_rounds = sum(len(matches) < min(board_count, player_count // 3) for matches in rounds.values())
        score = (
            max(0, partial_rounds - int(len(regular_matches) % min(board_count, player_count // 3) != 0)),
            sum(min(board_count, player_count // 3) - len(matches) for matches in rounds.values() if len(matches) < min(board_count, player_count // 3)),
            max(duties) - min(duties),
            sum(count * count for count in duties),
        )
        if best_score is None or score < best_score:
            best_schedule, best_score = schedule, score
            expected_spread = 1 if len(schedule) >= player_count else 0
            if score[0] == 0 and score[2] <= expected_spread:
                break

    if best_schedule is None:
        raise ScheduleError("Er kon geen geldig schema met een evenwichtige scheidsrechterverdeling worden gemaakt.")
    return best_schedule
