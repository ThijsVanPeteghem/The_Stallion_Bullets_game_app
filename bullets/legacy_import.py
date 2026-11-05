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
        ).casefold()
        for source, target in aliases.items()
    }

    aliased_evenings = deepcopy(evenings)
    for evening in aliased_evenings:
        # Determine which aliases would be safe to apply for this evening
        # An alias is safe if the source and target don't appear in the same match
        safe_aliases = {}
        for source, target in normalized_aliases.items():
            # Check if both source and target appear together in any match
            conflict = False
            for match in evening["matches"]:
                match_names = {
                    unicodedata.normalize("NFC", p["name"]).casefold()
                    for p in match["players"]
                }
                if source in match_names and target in match_names:
                    conflict = True
                    break
            if not conflict:
                safe_aliases[source] = target
        
        # Apply safe aliases
        def apply_safe_alias(name):
            normalized = unicodedata.normalize("NFC", name).casefold()
            if normalized in safe_aliases:
                # Return the casefold'd target, but we need the proper-cased version
                # For now, just return what's in safe_aliases
                return safe_aliases[normalized]
            return unicodedata.normalize("NFC", name)
        
        evening["players"] = list(
            dict.fromkeys(apply_safe_alias(name) for name in evening["players"])
        )
        evening["stroman"] = apply_safe_alias(evening["stroman"])
        
        for item in evening["matches"]:
            for p in item["players"]:
                p["name"] = apply_safe_alias(p["name"])
            item["referee"] = apply_safe_alias(item["referee"])
    
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


def parse_legacy_file(path, skip_player_count_validation=False):
    path = Path(path)
    # Ondersteun beide naamformaten:
    # - speeldagN_dd-mm-jjjj.txt (oud formaat voor 2025-2026)
    # - speeldagN__dd-mm-jjjj.txt (nieuw formaat voor 2026-2027)
    match = re.fullmatch(
        r"speeldag\d+_+(\d{2}-\d{2}-\d{4})\.txt",
        path.name,
        re.IGNORECASE,
    )
    if not match:
        raise LegacyImportError(
            f"{path.name}: bestandsnaam moet speeldagN_dd-mm-jjjj.txt of speeldagN__dd-mm-jjjj.txt zijn."
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
    block_round_counts = Counter()

    def finish_match():
        if current is None:
            return
        if len(current["players"]) != 2:
            raise LegacyImportError(
                f"{path.name}: wedstrijd {current['number']} moet precies twee spelers bevatten."
            )
        if current["players"][0]["name"] == current["players"][1]["name"]:
            raise LegacyImportError(
                f"{path.name}: wedstrijd {current['number']} bevat dezelfde speler twee keer: {current['players'][0]['name']!r}."
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
                "player_round_number": int(round_match.group(1)),
                "round_number": None,
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
            block_round_counts[current["board"]] += 1
            current["round_number"] = block_round_counts[current["board"]]
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
            referee_name = fields[1].strip() if len(fields) >= 2 else ""
            if not referee_name:
                if skip_player_count_validation:
                    # Bij legacy import: laat lege schrijvers toe en gebruik een default
                    referee_name = "Unknown"
                else:
                    raise LegacyImportError(
                        f"{path.name}:{line_number}: schrijversnaam ontbreekt."
                    )
            current["referee"] = unicodedata.normalize("NFC", referee_name)
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
    appearances = Counter(
        player["name"]
        for item in matches
        for player in item["players"]
    )
    highest_appearance_count = max(appearances.values())
    stroman_candidates = [
        name
        for name, count in appearances.items()
        if count == highest_appearance_count
    ]
    stroman_name = stroman_candidates[0] if len(stroman_candidates) == 1 else None
    match_count = highest_appearance_count - 1
    if not skip_player_count_validation:
        if (
            stroman_name is None
            or match_count < 1
            or any(
                count != (match_count + 1 if name == stroman_name else match_count)
                for name, count in appearances.items()
            )
        ):
            raise LegacyImportError(
                f"{path.name}: spelersaantallen kloppen niet; één speler moet precies één extra wedstrijd hebben."
            )
        last_match_players = matches[-1]["players"]
        if stroman_name not in {player["name"] for player in last_match_players}:
            raise LegacyImportError(
                f"{path.name}: de speler met één extra wedstrijd moet in de laatste wedstrijd staan."
            )
        marked_names = {
            player["name"]
            for item in matches
            for player in item["players"]
            if player["is_stroman"]
        }
        if marked_names and marked_names != {stroman_name}:
            raise LegacyImportError(
                f"{path.name}: de *-markering komt niet overeen met de speler met één extra wedstrijd."
            )
    else:
        # Bij skip_player_count_validation: bepaal stroman op basis van merkeringen
        marked_names = {
            player["name"]
            for item in matches
            for player in item["players"]
            if player["is_stroman"]
        }
        if len(marked_names) == 1:
            stroman_name = marked_names.pop()
        elif len(marked_names) == 0:
            # Geen markeringen; selecteer de speler met de meeste verschijningen
            if appearances:
                stroman_name = max(appearances.items(), key=lambda x: x[1])[0]
            else:
                stroman_name = None
        else:
            # Meerdere markeringen; dit is een fout
            raise LegacyImportError(
                f"{path.name}: meerdere spelers gemarkeerd met *; slechts één toegestaan."
            )
    for item in matches:
        for player in item["players"]:
            player["is_stroman"] = (
                item is matches[-1] and player["name"] == stroman_name
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
        if item["referee"] and item["referee"] != "Unknown" and not item["referee"].isdigit()
    }
    if not referee_names.issubset(set(player_order)):
        raise LegacyImportError(
            f"{path.name}: een of meer schrijvers komen niet voor als aanwezige speler."
        )

    round_players = {}
    player_round_players = {}
    for item in matches:
        used = round_players.setdefault(item["round_number"], set())
        participants = {player["name"] for player in item["players"]}
        if used.intersection(participants):
            raise LegacyImportError(
                f"{path.name}: een speler komt meerdere keren voor in ronde {item['round_number']}."
            )
        used.update(participants)
        used_player_round = player_round_players.setdefault(
            item["player_round_number"], set()
        )
        if used_player_round.intersection(participants):
            raise LegacyImportError(
                f"{path.name}: een speler komt meerdere keren voor in spelersronde "
                f"{item['player_round_number']}."
            )
        used_player_round.update(participants)

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
        
        # Voeg ook scheidsrechters toe aan player_records als ze niet al voorkomen
        for match in item["matches"]:
            referee_name = match["referee"]
            if referee_name and referee_name not in player_records:
                key = unicodedata.normalize("NFC", referee_name).casefold()
                if key not in players_by_key:
                    players_by_key[key] = Player.objects.create(name=referee_name)
                player_records[referee_name] = players_by_key[key]
        
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
                try:
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
                except Exception as e:
                    raise LegacyImportError(
                        f"Match {item_match['number']} in avond {item['date']}: "
                        f"fout bij speler {player_data['name']}: {str(e)}"
                    ) from e
        imported.append(evening)
    return imported
