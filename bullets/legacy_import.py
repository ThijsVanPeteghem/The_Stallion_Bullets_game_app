from collections import Counter
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import re
import unicodedata

from django.db import transaction

from .models import Attendance, Evening, Match, MatchPlayerStats, Player, Season


class LegacyImportError(ValueError):
    pass


def apply_player_aliases(evenings, aliases):
    normalized_aliases = {
        unicodedata.normalize("NFC", source).casefold(): unicodedata.normalize(
            "NFC", target
        )
        for source, target in aliases.items()
    }

    def canonical_name(name):
        return normalized_aliases.get(
            unicodedata.normalize("NFC", name).casefold(),
            unicodedata.normalize("NFC", name),
        )

    aliased_evenings = deepcopy(evenings)
    for evening in aliased_evenings:
        evening["players"] = list(
            dict.fromkeys(canonical_name(name) for name in evening["players"])
        )
        evening["stroman"] = canonical_name(evening["stroman"])
        for item in evening["matches"]:
            item["referee"] = canonical_name(item["referee"])
            for player in item["players"]:
                player["name"] = canonical_name(player["name"])
    return aliased_evenings


def _integer(value, *, filename, line_number, field, allow_blank=False):
    value = value.strip()
    if not value and allow_blank:
        return 0
    try:
        return int(value)
    except ValueError as error:
        raise LegacyImportError(
            f"{filename}:{line_number}: ongeldige waarde voor {field}: {value!r}."
        ) from error


def _parse_player(fields, *, name_index, values_index, filename, line_number):
    fields = fields + [""] * max(0, values_index + 5 - len(fields))
    name = unicodedata.normalize("NFC", fields[name_index].strip())
    is_stroman = name.endswith("*")
    if is_stroman:
        name = name[:-1].strip()
    if not name:
        raise LegacyImportError(
            f"{filename}:{line_number}: spelernaam ontbreekt."
        )

    values = fields[values_index:values_index + 5]
    legs = _integer(
        values[0], filename=filename, line_number=line_number, field="legs"
    )
    scores_180 = _integer(
        values[1], filename=filename, line_number=line_number, field="180",
        allow_blank=True,
    )
    scores_171 = _integer(
        values[2], filename=filename, line_number=line_number, field="171",
        allow_blank=True,
    )
    finish = values[3].strip()
    darts = values[4].strip()
    if finish:
        finish_values = [
            _integer(
                item,
                filename=filename,
                line_number=line_number,
                field="HF",
            )
            for item in finish.split(",")
        ]
        if any(value < 2 or value > 170 for value in finish_values):
            raise LegacyImportError(
                f"{filename}:{line_number}: HF-waarde moet tussen 2 en 170 liggen."
            )
        finish = ", ".join(str(value) for value in finish_values)
    if darts:
        dart_values = [
            _integer(
                item,
                filename=filename,
                line_number=line_number,
                field="MP",
            )
            for item in darts.split(",")
        ]
        if any(value < 1 or value > 99 for value in dart_values):
            raise LegacyImportError(
                f"{filename}:{line_number}: MP-waarde moet tussen 1 en 99 liggen."
            )
        darts = ", ".join(str(value) for value in dart_values)

    return {
        "name": name,
        "is_stroman": is_stroman,
        "legs_won": legs,
        "scores_180": scores_180,
        "scores_171": scores_171,
        "high_finishes": finish,
        "least_darts": darts,
    }


def parse_legacy_file(path):
    path = Path(path)
    match = re.fullmatch(
        r"speeldag\d+__(\d{2}-\d{2}-\d{4})\.txt",
        path.name,
        re.IGNORECASE,
    )
    if not match:
        raise LegacyImportError(
            f"{path.name}: bestandsnaam moet speeldagN__dd-mm-jjjj.txt zijn."
        )
    try:
        date = datetime.strptime(match.group(1), "%d-%m-%Y").date()
    except ValueError as error:
        raise LegacyImportError(f"{path.name}: ongeldige datum.") from error

    try:
        lines = path.read_bytes().decode("cp1252").splitlines()
    except OSError as error:
        raise LegacyImportError(f"{path}: bestand kan niet worden gelezen.") from error

    matches = []
    current = None
    awaiting_second_player = False

    def finish_match():
        if current is None:
            return
        if len(current["players"]) != 2:
            raise LegacyImportError(
                f"{path.name}: wedstrijd {current['number']} moet precies twee spelers bevatten."
            )
        if current["referee"] is None:
            raise LegacyImportError(
                f"{path.name}: wedstrijd {current['number']} heeft geen schrijver."
            )
        if sum(player["legs_won"] for player in current["players"]) != 3:
            raise LegacyImportError(
                f"{path.name}: wedstrijd {current['number']} heeft geen score van exact 3 legs."
            )
        matches.append(current.copy())

    for line_number, line in enumerate(lines, start=1):
        fields = line.strip().split("\t")
        first = fields[0].strip()
        match_header = re.fullmatch(r"W(\d+)", first, re.IGNORECASE)
        if match_header:
            finish_match()
            round_match = re.search(r"\bRONDE\s+(\d+)", line, re.IGNORECASE)
            if not round_match:
                raise LegacyImportError(
                    f"{path.name}:{line_number}: speelronde ontbreekt."
                )
            current = {
                "number": int(match_header.group(1)),
                "round_number": int(round_match.group(1)),
                "board": None,
                "players": [],
                "referee": None,
            }
            awaiting_second_player = False
            continue

        if current is None:
            continue
        if first.startswith("Blok "):
            try:
                current["board"] = int(first.split()[1])
            except (IndexError, ValueError) as error:
                raise LegacyImportError(
                    f"{path.name}:{line_number}: ongeldig bloknummer."
                ) from error
            current["players"].append(
                _parse_player(
                    fields,
                    name_index=1,
                    values_index=2,
                    filename=path.name,
                    line_number=line_number,
                )
            )
            awaiting_second_player = True
        elif first.casefold().startswith("schrijver"):
            if len(fields) < 2 or not fields[1].strip():
                raise LegacyImportError(
                    f"{path.name}:{line_number}: schrijversnaam ontbreekt."
                )
            current["referee"] = unicodedata.normalize("NFC", fields[1].strip())
            awaiting_second_player = False
        elif awaiting_second_player and first:
            current["players"].append(
                _parse_player(
                    fields,
                    name_index=0,
                    values_index=1,
                    filename=path.name,
                    line_number=line_number,
                )
            )
            awaiting_second_player = False

    finish_match()
    if not matches:
        raise LegacyImportError(f"{path.name}: geen wedstrijden gevonden.")

    numbers = [item["number"] for item in matches]
    if numbers != list(range(1, len(matches) + 1)):
        raise LegacyImportError(f"{path.name}: wedstrijdnummers zijn niet aaneengesloten.")
    if sum(player["is_stroman"] for item in matches for player in item["players"]) != 1:
        raise LegacyImportError(
            f"{path.name}: verwacht precies één speler die als stroman is gemarkeerd."
        )
    if not matches[-1]["players"][0]["is_stroman"] and not matches[-1]["players"][1]["is_stroman"]:
        raise LegacyImportError(
            f"{path.name}: de stroman moet de laatste wedstrijd spelen."
        )

    appearances = Counter(
        player["name"]
        for item in matches
        for player in item["players"]
    )
    stroman_name = next(
        player["name"]
        for item in matches
        for player in item["players"]
        if player["is_stroman"]
    )
    regular_counts = [
        count for name, count in appearances.items() if name != stroman_name
    ]
    match_count = Counter(regular_counts).most_common(1)[0][0]
    if (
        any(count != match_count for name, count in appearances.items() if name != stroman_name)
        or appearances[stroman_name] != match_count + 1
    ):
        raise LegacyImportError(
            f"{path.name}: spelersaantallen kloppen niet; alleen de stroman hoort één extra wedstrijd te spelen."
        )

    player_order = list(
        dict.fromkeys(
            player["name"]
            for item in matches
            for player in item["players"]
        )
    )
    referee_names = {
        item["referee"]
        for item in matches
    }
    if not referee_names.issubset(set(player_order)):
        raise LegacyImportError(
            f"{path.name}: een of meer schrijvers komen niet voor als aanwezige speler."
        )

    round_players = {}
    for item in matches:
        used = round_players.setdefault(item["round_number"], set())
        participants = {player["name"] for player in item["players"]}
        if used.intersection(participants):
            raise LegacyImportError(
                f"{path.name}: een speler komt meerdere keren voor in ronde {item['round_number']}."
            )
        used.update(participants)

    return {
        "date": date,
        "matches": matches,
        "players": player_order,
        "match_count": match_count,
        "stroman": stroman_name,
        "board_count": max(item["board"] for item in matches),
        "name": path.name,
    }


@transaction.atomic
def import_legacy_evenings(evenings, season_name):
    season, _ = Season.objects.get_or_create(name=season_name)
    if Evening.objects.filter(season=season, date__in=[item["date"] for item in evenings]).exists():
        raise LegacyImportError(
            "Een of meer avonden uit de bronbestanden bestaan al in dit seizoen. Er is niets geïmporteerd."
        )

    players_by_key = {
        unicodedata.normalize("NFC", player.name).casefold(): player
        for player in Player.objects.all()
    }

    imported = []
    for item in evenings:
        for name in item["players"]:
            key = unicodedata.normalize("NFC", name).casefold()
            if key not in players_by_key:
                players_by_key[key] = Player.objects.create(name=name)

        evening = Evening.objects.create(
            season=season,
            date=item["date"],
            board_count=item["board_count"],
            match_count=item["match_count"],
        )
        player_records = {
            name: players_by_key[unicodedata.normalize("NFC", name).casefold()]
            for name in item["players"]
        }
        for draw_order, name in enumerate(item["players"], start=1):
            Attendance.objects.create(
                evening=evening,
                player=player_records[name],
                draw_order=draw_order,
            )

        for item_match in item["matches"]:
            match_record = Match.objects.create(
                evening=evening,
                number=item_match["number"],
                round_number=item_match["round_number"],
                board=item_match["board"],
                player1=player_records[item_match["players"][0]["name"]],
                player2=player_records[item_match["players"][1]["name"]],
                referee=player_records[item_match["referee"]],
            )
            for player_data in item_match["players"]:
                MatchPlayerStats.objects.create(
                    match=match_record,
                    player=player_records[player_data["name"]],
                    is_stroman=player_data["is_stroman"],
                    legs_won=player_data["legs_won"],
                    scores_180=player_data["scores_180"],
                    scores_171=player_data["scores_171"],
                    high_finishes=player_data["high_finishes"],
                    least_darts=player_data["least_darts"],
                )
        imported.append(evening)
    return imported
