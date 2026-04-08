from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import replace
from pathlib import Path

import requests

from lineup import is_bench_position
from models import Player, RosterSnapshot

MLB_BASE = "https://statsapi.mlb.com/api/v1"
PROJECT_ROOT = Path(__file__).resolve().parent
SFBB_ID_MAP_PATH = PROJECT_ROOT / "data" / "yahoo_mlb_id_map_sfbb.csv"
LOCAL_ID_MAP_PATH = PROJECT_ROOT / "data" / "yahoo_mlb_id_map.csv"

TEAM_ABBR_TO_MLB_ID = {
    "ARI": 109,
    "ATL": 144,
    "BAL": 110,
    "BOS": 111,
    "CHC": 112,
    "CWS": 145,
    "CIN": 113,
    "CLE": 114,
    "COL": 115,
    "DET": 116,
    "HOU": 117,
    "KC": 118,
    "LAA": 108,
    "LAD": 119,
    "MIA": 146,
    "MIL": 158,
    "MIN": 142,
    "NYM": 121,
    "NYY": 147,
    "OAK": 133,
    "ATH": 133,
    "PHI": 143,
    "PIT": 134,
    "SD": 135,
    "SEA": 136,
    "SF": 137,
    "STL": 138,
    "TB": 139,
    "TEX": 140,
    "TOR": 141,
    "WSH": 120,
    "AZ": 109,
    "WSN": 120,
    "CHW": 145,
    "SDP": 135,
    "SFG": 137,
    "TBR": 139,
    "KCR": 118,
}

_SCHEDULE_CACHE: dict[str, list] = {}
_TEAM_ROSTER_CACHE: dict[tuple[int, str], list] = {}
_TEAM_GAME_CACHE: dict[tuple[str, int], dict | None] = {}
_GAME_BOXSCORE_CACHE: dict[int, dict] = {}
_MLB_PERSON_ID_CACHE: dict[tuple[str, int, str], str | None] = {}
_STARTING_HITTER_IDS_CACHE: dict[tuple[int, int], set[str]] = {}
_PROBABLE_PITCHER_CACHE: dict[tuple[int, int], str | None] = {}
_PITCHER_ROLE_CACHE: dict[tuple[str, int], str | None] = {}
_LOCAL_ID_MAP_CACHE: dict[str, dict] | None = None
_LOCAL_ID_NAME_CACHE: dict[tuple[str, str], dict] | None = None

STATUS_LABELS = {
    "starting": "starting",
    "not_starting": "not starting",
    "no_game": "no game",
    "lineup_pending": "lineup pending",
    "probable_pitcher_missing": "probable pitcher missing",
    "reliever": "reliever",
    "team_unmapped": "team unmapped",
    "player_unmapped": "player unmapped",
    "inactive_slot": "inactive slot",
}


def normalize_name(name: str | None) -> str:
    if not name:
        return ""
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower().strip().replace(".", "")
    normalized = re.sub(r"\s*\((batter|pitcher)\)\s*", " ", normalized)
    normalized = normalized.replace("’", "'")
    normalized = normalized.replace("'", "")
    normalized = re.sub(r"\bjr\b", "jr", normalized)
    normalized = re.sub(r"\bii\b", "ii", normalized)
    normalized = re.sub(r"\biii\b", "iii", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _log(verbose: bool, *args) -> None:
    if verbose:
        print(*args)


def _status_result(
    is_starting_today: bool | None,
    reason: str,
) -> tuple[bool | None, str]:
    return is_starting_today, reason


def load_local_id_map(path: Path = LOCAL_ID_MAP_PATH) -> dict[str, dict]:
    global _LOCAL_ID_MAP_CACHE
    if _LOCAL_ID_MAP_CACHE is not None:
        return _LOCAL_ID_MAP_CACHE

    rows: dict[str, dict] = {}
    for source_path in (SFBB_ID_MAP_PATH, path):
        if not source_path.exists():
            continue
        with source_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                yahoo_player_id = (row.get("yahoo_player_id") or "").strip()
                if not yahoo_player_id:
                    continue
                existing = rows.get(yahoo_player_id, {}).copy()
                merged = existing if existing else {"yahoo_player_id": yahoo_player_id}
                for key, value in row.items():
                    if value not in (None, ""):
                        merged[key] = value
                rows[yahoo_player_id] = merged
    _LOCAL_ID_MAP_CACHE = rows
    return rows


def load_local_id_name_map(path: Path = LOCAL_ID_MAP_PATH) -> dict[tuple[str, str], dict]:
    global _LOCAL_ID_NAME_CACHE
    if _LOCAL_ID_NAME_CACHE is not None:
        return _LOCAL_ID_NAME_CACHE

    name_map: dict[tuple[str, str], dict] = {}
    for row in load_local_id_map(path).values():
        yahoo_name = normalize_name(row.get("yahoo_name") or row.get("mlb_name") or "")
        team_abbr = (row.get("team_abbr") or "").strip().upper()
        mlb_person_id = (row.get("mlb_person_id") or "").strip()
        if not yahoo_name or not mlb_person_id:
            continue
        name_map[(yahoo_name, team_abbr)] = row
    _LOCAL_ID_NAME_CACHE = name_map
    return name_map


def lookup_local_mlb_person_id(player: Player) -> str | None:
    row = load_local_id_map().get(player.player_id)
    if row:
        mlb_person_id = (row.get("mlb_person_id") or "").strip()
        if mlb_person_id:
            return mlb_person_id

    fallback_row = load_local_id_name_map().get(
        (normalize_name(player.name), (player.editorial_team_abbr or "").strip().upper())
    )
    if not fallback_row:
        return None
    mlb_person_id = (fallback_row.get("mlb_person_id") or "").strip()
    return mlb_person_id or None


def export_roster_crosswalk_template(
    roster: RosterSnapshot,
    path: Path = LOCAL_ID_MAP_PATH,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_local_id_map(path)
    fieldnames = [
        "yahoo_player_id",
        "yahoo_name",
        "team_abbr",
        "mlb_person_id",
        "mlb_name",
        "notes",
    ]

    rows: dict[str, dict] = {key: value.copy() for key, value in existing.items()}
    for player in roster.players:
        rows.setdefault(
            player.player_id,
            {
                "yahoo_player_id": player.player_id,
                "yahoo_name": player.name,
                "team_abbr": player.editorial_team_abbr or "",
                "mlb_person_id": "",
                "mlb_name": "",
                "notes": "",
            },
        )

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for yahoo_player_id in sorted(rows):
            writer.writerow(rows[yahoo_player_id])

    clear_caches()
    return path


def get_schedule_for_date(date_str: str) -> list:
    if date_str in _SCHEDULE_CACHE:
        return _SCHEDULE_CACHE[date_str]

    response = requests.get(
        f"{MLB_BASE}/schedule",
        params={"sportId": 1, "date": date_str, "hydrate": "probablePitcher"},
        timeout=30,
    )
    response.raise_for_status()
    games = response.json().get("dates", [{}])[0].get("games", [])
    _SCHEDULE_CACHE[date_str] = games
    return games


def get_team_roster(team_id: int, date_str: str) -> list:
    cache_key = (team_id, date_str)
    if cache_key in _TEAM_ROSTER_CACHE:
        return _TEAM_ROSTER_CACHE[cache_key]

    response = requests.get(
        f"{MLB_BASE}/teams/{team_id}/roster",
        params={"date": date_str},
        timeout=30,
    )
    response.raise_for_status()
    roster = response.json().get("roster", [])
    _TEAM_ROSTER_CACHE[cache_key] = roster
    return roster


def find_mlb_person_id(full_name: str, team_id: int, date_str: str, verbose: bool = False) -> str | None:
    cache_key = (normalize_name(full_name), team_id, date_str)
    if cache_key in _MLB_PERSON_ID_CACHE:
        return _MLB_PERSON_ID_CACHE[cache_key]

    roster = get_team_roster(team_id, date_str)
    target = normalize_name(full_name)
    _log(verbose, f"Matching MLB roster name for {full_name}")

    for row in roster:
        person = row.get("person", {})
        if normalize_name(person.get("fullName")) == target:
            result = str(person.get("id"))
            _MLB_PERSON_ID_CACHE[cache_key] = result
            return result

    _MLB_PERSON_ID_CACHE[cache_key] = None
    return None


def find_player_mlb_person_id(player: Player, date_str: str, verbose: bool = False) -> str | None:
    if not player.editorial_team_abbr or player.editorial_team_abbr not in TEAM_ABBR_TO_MLB_ID:
        return None

    local_mlb_person_id = lookup_local_mlb_person_id(player)
    if local_mlb_person_id is not None:
        _log(verbose, f"Matched {player.name} from local yahoo->mlb CSV: {local_mlb_person_id}")
        return local_mlb_person_id

    mlb_team_id = TEAM_ABBR_TO_MLB_ID[player.editorial_team_abbr]
    return find_mlb_person_id(player.name, mlb_team_id, date_str, verbose=verbose)


def get_team_game(date_str: str, team_id: int) -> dict | None:
    cache_key = (date_str, team_id)
    if cache_key in _TEAM_GAME_CACHE:
        return _TEAM_GAME_CACHE[cache_key]

    for game in get_schedule_for_date(date_str):
        away_id = game["teams"]["away"]["team"]["id"]
        home_id = game["teams"]["home"]["team"]["id"]
        if away_id == team_id or home_id == team_id:
            _TEAM_GAME_CACHE[cache_key] = game
            return game

    _TEAM_GAME_CACHE[cache_key] = None
    return None


def get_game_boxscore(game_pk: int) -> dict:
    if game_pk in _GAME_BOXSCORE_CACHE:
        return _GAME_BOXSCORE_CACHE[game_pk]

    response = requests.get(f"{MLB_BASE}/game/{game_pk}/boxscore", timeout=30)
    response.raise_for_status()
    payload = response.json()
    _GAME_BOXSCORE_CACHE[game_pk] = payload
    return payload


def get_team_starting_hitter_ids(game_pk: int, team_id: int) -> set[str]:
    cache_key = (game_pk, team_id)
    if cache_key in _STARTING_HITTER_IDS_CACHE:
        return _STARTING_HITTER_IDS_CACHE[cache_key]

    boxscore = get_game_boxscore(game_pk)
    for side in ("away", "home"):
        team_block = boxscore["teams"][side]
        if team_block["team"]["id"] != team_id:
            continue
        batting_order = team_block.get("battingOrder", []) or []
        result = {str(player_id) for player_id in batting_order}
        _STARTING_HITTER_IDS_CACHE[cache_key] = result
        return result

    _STARTING_HITTER_IDS_CACHE[cache_key] = set()
    return set()


def get_team_probable_pitcher_id(game: dict, team_id: int) -> str | None:
    cache_key = (game["gamePk"], team_id)
    if cache_key in _PROBABLE_PITCHER_CACHE:
        return _PROBABLE_PITCHER_CACHE[cache_key]

    result = None
    if game["teams"]["away"]["team"]["id"] == team_id:
        probable = game["teams"]["away"].get("probablePitcher", {})
        if probable.get("id") is not None:
            result = str(probable["id"])
    elif game["teams"]["home"]["team"]["id"] == team_id:
        probable = game["teams"]["home"].get("probablePitcher", {})
        if probable.get("id") is not None:
            result = str(probable["id"])

    _PROBABLE_PITCHER_CACHE[cache_key] = result
    return result


def get_pitcher_role(mlb_person_id: str, season: int) -> str | None:
    cache_key = (mlb_person_id, season)
    if cache_key in _PITCHER_ROLE_CACHE:
        return _PITCHER_ROLE_CACHE[cache_key]

    response = requests.get(
        f"{MLB_BASE}/people/{mlb_person_id}/stats",
        params={"stats": "season", "group": "pitching", "season": str(season), "sportIds": 1},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    stat_blocks = payload.get("stats") or []
    if not stat_blocks:
        _PITCHER_ROLE_CACHE[cache_key] = None
        return None
    splits = stat_blocks[0].get("splits") or []
    if not splits:
        _PITCHER_ROLE_CACHE[cache_key] = None
        return None

    stat_line = splits[0].get("stat") or {}
    starts = int(stat_line.get("gamesStarted") or 0)
    appearances = int(stat_line.get("gamesPlayed") or 0)
    saves = int(stat_line.get("saves") or 0)
    holds = int(stat_line.get("holds") or 0)

    role = None
    if starts == 0 and appearances > 0:
        role = "reliever"
    elif saves + holds > 0 and starts == 0:
        role = "reliever"
    elif starts > 0:
        role = "starter"

    _PITCHER_ROLE_CACHE[cache_key] = role
    return role


def yahoo_player_is_starting(
    player: Player,
    date_str: str,
    verbose: bool = False,
) -> tuple[bool | None, str]:
    if not player.editorial_team_abbr or player.editorial_team_abbr not in TEAM_ABBR_TO_MLB_ID:
        _log(verbose, f"Could not map team abbreviation for {player.name}: {player.editorial_team_abbr}")
        return _status_result(None, "team_unmapped")

    if player.status in {"IL10", "IL15", "IL60", "NA"} or is_bench_position(player.selected_position):
        if player.selected_position in {"IL", "NA"}:
            return _status_result(None, "inactive_slot")

    mlb_team_id = TEAM_ABBR_TO_MLB_ID[player.editorial_team_abbr]
    game = get_team_game(date_str, mlb_team_id)
    if game is None:
        _log(verbose, f"No MLB game found for {player.name} on {date_str}")
        return _status_result(None, "no_game")

    position_type = player.position_type or ""
    primary_position = player.primary_position or ""

    if position_type == "P" and primary_position == "RP":
        return _status_result(None, "reliever")

    mlb_person_id = find_player_mlb_person_id(player, date_str, verbose=verbose)
    if mlb_person_id is None:
        _log(verbose, f"Could not map MLB person id for {player.name}")
        return _status_result(None, "player_unmapped")

    if position_type == "P":
        if primary_position == "P":
            inferred_role = get_pitcher_role(mlb_person_id, int(date_str[:4]))
            if inferred_role == "reliever":
                return _status_result(None, "reliever")
        probable_pitcher_id = get_team_probable_pitcher_id(game, mlb_team_id)
        if probable_pitcher_id is None:
            return _status_result(None, "probable_pitcher_missing")
        return _status_result(mlb_person_id == probable_pitcher_id, "starting" if mlb_person_id == probable_pitcher_id else "not_starting")

    starter_ids = get_team_starting_hitter_ids(game["gamePk"], mlb_team_id)
    if not starter_ids:
        return _status_result(None, "lineup_pending")
    is_starting = mlb_person_id in starter_ids
    return _status_result(is_starting, "starting" if is_starting else "not_starting")


def enrich_roster_with_starting_status(
    roster: RosterSnapshot,
    date_str: str | None = None,
    verbose: bool = False,
    ignore_locks: bool = False,
) -> RosterSnapshot:
    target_date = date_str or roster.lineup_date
    if not target_date:
        raise ValueError("A lineup date is required to enrich the roster.")

    players = [
        replace(
            player,
            is_starting_today=status[0],
            starting_status_reason=status[1],
            is_locked=False if ignore_locks else player.is_locked,
        )
        for player, status in [
            (
                player,
                yahoo_player_is_starting(player=player, date_str=target_date, verbose=verbose),
            )
            for player in roster.players
        ]
    ]
    return replace(roster, lineup_date=target_date, players=players)


def describe_starting_status(player: Player) -> str:
    if player.is_starting_today is True:
        return "starting"
    if player.is_starting_today is False:
        return "not starting"
    return STATUS_LABELS.get(player.starting_status_reason or "", "unknown")


def clear_caches() -> None:
    global _LOCAL_ID_MAP_CACHE, _LOCAL_ID_NAME_CACHE
    _SCHEDULE_CACHE.clear()
    _TEAM_ROSTER_CACHE.clear()
    _TEAM_GAME_CACHE.clear()
    _GAME_BOXSCORE_CACHE.clear()
    _MLB_PERSON_ID_CACHE.clear()
    _STARTING_HITTER_IDS_CACHE.clear()
    _PROBABLE_PITCHER_CACHE.clear()
    _PITCHER_ROLE_CACHE.clear()
    _LOCAL_ID_MAP_CACHE = None
    _LOCAL_ID_NAME_CACHE = None
