from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
import xml.etree.ElementTree as ET
from typing import Iterable

import requests

from auth import load_token_file, refresh_access_token, save_token_file
from config import AppConfig
from league_profiles import get_league_profile
from lineup import DEFAULT_SLOT_LIMITS
from models import MatchupCategory, MatchupCategoryDelta, MatchupSnapshot, PlannedMove, Player, RosterSnapshot
from utils import find_child_text, local_name

BASE_URL = "https://fantasysports.yahooapis.com/fantasy/v2"


class YahooFantasyClient:
    def __init__(self, config: AppConfig):
        self.config = config
        self.session = requests.Session()
        self._player_percent_started_cache: dict[str, int | None] = {}
        self._player_percent_owned_cache: dict[str, int | None] = {}
        self._player_average_pick_cache: dict[str, float | None] = {}
        self._player_actual_rank_last_week_cache: dict[tuple[str, str | None], int | None] = {}
        self._league_stat_categories_cache: dict[str, dict] | None = None
        self._league_roster_slot_limits_cache: dict[str, int] | None = None
        self.token = self._load_or_refresh_token()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.token['access_token']}",
                "Accept": "application/xml",
                "Content-Type": "application/xml",
            }
        )

    def _load_or_refresh_token(self) -> dict:
        token = load_token_file(self.config.yahoo_token_file) or {}
        if self.config.yahoo_access_token:
            token["access_token"] = self.config.yahoo_access_token
        if self.config.yahoo_refresh_token:
            token["refresh_token"] = self.config.yahoo_refresh_token

        refresh_token = token.get("refresh_token")
        if not refresh_token:
            raise RuntimeError(
                "No Yahoo refresh token is available. Run auth.py first or set YAHOO_REFRESH_TOKEN."
            )

        refreshed = refresh_access_token(
            client_id=self.config.yahoo_client_id,
            client_secret=self.config.yahoo_client_secret,
            redirect_uri=self.config.yahoo_redirect_uri,
            refresh_token=refresh_token,
        )
        merged = {**token, **refreshed}
        save_token_file(self.config.yahoo_token_file, merged)
        return merged

    def get_team_roster(self, lineup_date: str) -> RosterSnapshot:
        response = self.session.get(
            f"{BASE_URL}/team/{self.config.yahoo_team_key}/roster;date={lineup_date}",
            timeout=30,
        )
        response.raise_for_status()
        roster = parse_roster_xml(response.text)
        roster = replace(
            roster,
            league_profile_key=self.config.league_profile_key,
            slot_limits=self.get_league_roster_slot_limits(),
        )
        return self._populate_player_yahoo_metrics(roster)

    def set_lineup(self, lineup_date: str, moves: Iterable[PlannedMove]) -> None:
        xml_body = build_roster_update_xml(lineup_date=lineup_date, moves=list(moves))
        response = self.session.put(
            f"{BASE_URL}/team/{self.config.yahoo_team_key}/roster",
            data=xml_body.encode("utf-8"),
            timeout=30,
        )
        response.raise_for_status()

    def get_league_stat_categories(self) -> dict[str, dict]:
        if self._league_stat_categories_cache is not None:
            return self._league_stat_categories_cache
        league_key = ".".join(self.config.yahoo_team_key.split(".")[:3])
        response = self.session.get(
            f"{BASE_URL}/league/{league_key}/settings",
            timeout=30,
        )
        response.raise_for_status()
        self._league_stat_categories_cache = parse_league_stat_categories(response.text)
        return self._league_stat_categories_cache

    def get_league_roster_slot_limits(self) -> dict[str, int]:
        if self._league_roster_slot_limits_cache is not None:
            return self._league_roster_slot_limits_cache
        league_key = ".".join(self.config.yahoo_team_key.split(".")[:3])
        response = self.session.get(
            f"{BASE_URL}/league/{league_key}/settings",
            timeout=30,
        )
        response.raise_for_status()
        parsed = parse_league_roster_positions(response.text)
        profile = get_league_profile(self.config.league_profile_key)
        fallback_limits = {slot: DEFAULT_SLOT_LIMITS[slot] for slot in profile.active_slot_order if slot in DEFAULT_SLOT_LIMITS}
        self._league_roster_slot_limits_cache = parsed or fallback_limits or DEFAULT_SLOT_LIMITS.copy()
        return self._league_roster_slot_limits_cache

    def get_current_matchup(self) -> MatchupSnapshot | None:
        response = self.session.get(
            f"{BASE_URL}/team/{self.config.yahoo_team_key}/matchups;weeks=current",
            timeout=30,
        )
        response.raise_for_status()
        stat_categories = self.get_league_stat_categories()
        return parse_current_matchup_xml(response.text, self.config.yahoo_team_key, stat_categories)

    def get_current_matchup_deltas(self) -> dict[str, MatchupCategoryDelta]:
        matchup = self.get_current_matchup()
        if matchup is None:
            return {}
        return build_matchup_delta_map(matchup)

    def _populate_player_yahoo_metrics(self, roster: RosterSnapshot) -> RosterSnapshot:
        actual_rank_last_week = self.get_actual_rank_last_week_map(
            [player.player_key for player in roster.players],
            lineup_date=roster.lineup_date,
        )
        players = []
        for player in roster.players:
            players.append(
                replace(
                    player,
                    yahoo_average_pick=self.get_player_average_pick(player.player_key),
                    yahoo_actual_rank_last_week=actual_rank_last_week.get(player.player_key),
                    yahoo_percent_started=self.get_player_percent_started(player.player_key),
                    yahoo_percent_owned=self.get_player_percent_owned(player.player_key),
                )
            )
        return replace(roster, players=players)

    def get_player_percent_started(self, player_key: str) -> int | None:
        if player_key not in self._player_percent_started_cache:
            self._player_percent_started_cache[player_key] = self._fetch_player_metric(player_key, "percent_started")
        return self._player_percent_started_cache[player_key]

    def get_player_percent_owned(self, player_key: str) -> int | None:
        if player_key not in self._player_percent_owned_cache:
            self._player_percent_owned_cache[player_key] = self._fetch_player_metric(player_key, "percent_owned")
        return self._player_percent_owned_cache[player_key]

    def get_player_average_pick(self, player_key: str) -> float | None:
        if player_key not in self._player_average_pick_cache:
            self._player_average_pick_cache[player_key] = self._fetch_player_average_pick(player_key)
        return self._player_average_pick_cache[player_key]

    def get_actual_rank_last_week_map(
        self,
        player_keys: list[str],
        *,
        lineup_date: str | None = None,
    ) -> dict[str, int | None]:
        cache_keys = {(player_key, lineup_date): player_key for player_key in player_keys}
        missing_keys = [
            player_key
            for cache_key, player_key in cache_keys.items()
            if cache_key not in self._player_actual_rank_last_week_cache
        ]
        if missing_keys:
            fetched = self._fetch_actual_rank_last_week_map(missing_keys, lineup_date=lineup_date)
            for player_key in missing_keys:
                self._player_actual_rank_last_week_cache[(player_key, lineup_date)] = fetched.get(player_key)
        return {
            player_key: self._player_actual_rank_last_week_cache.get((player_key, lineup_date))
            for player_key in player_keys
        }

    def _fetch_player_metric(self, player_key: str, resource: str) -> int | None:
        response = self.session.get(
            f"{BASE_URL}/player/{player_key}/{resource}",
            timeout=30,
        )
        if response.status_code >= 400:
            return None
        return parse_metric_value(response.text, resource)

    def _fetch_player_average_pick(self, player_key: str) -> float | None:
        response = self.session.get(
            f"{BASE_URL}/player/{player_key}/draft_analysis",
            timeout=30,
        )
        if response.status_code >= 400:
            return None
        return parse_average_pick(response.text)

    def _fetch_actual_rank_last_week_map(
        self,
        player_keys: list[str],
        *,
        lineup_date: str | None = None,
    ) -> dict[str, int | None]:
        if not player_keys:
            return {}
        if lineup_date:
            return self._fetch_actual_rank_window_map(player_keys, lineup_date)
        team_key_parts = self.config.yahoo_team_key.split(".")
        league_key = ".".join(team_key_parts[:3])
        response = self.session.get(
            f"{BASE_URL}/league/{league_key}/players;player_keys={','.join(player_keys)};sort=AR;sort_type=lastweek",
            timeout=30,
        )
        if response.status_code >= 400:
            return {}
        return parse_player_order_map(response.text)

    def _fetch_actual_rank_window_map(self, player_keys: list[str], lineup_date: str) -> dict[str, int | None]:
        team_key_parts = self.config.yahoo_team_key.split(".")
        league_key = ".".join(team_key_parts[:3])
        end_date = date.fromisoformat(lineup_date)
        start_date = end_date - timedelta(days=6)
        daily_ranks: dict[str, list[int]] = {player_key: [] for player_key in player_keys}
        bottom_rank = len(player_keys) + 1

        current = start_date
        while current <= end_date:
            response = self.session.get(
                f"{BASE_URL}/league/{league_key}/players;player_keys={','.join(player_keys)};sort=AR;sort_type=date;sort_date={current.isoformat()}",
                timeout=30,
            )
            if response.status_code >= 400:
                current += timedelta(days=1)
                continue
            daily_order = parse_player_order_map(response.text)
            for player_key in player_keys:
                daily_ranks[player_key].append(daily_order.get(player_key, bottom_rank))
            current += timedelta(days=1)

        if not any(daily_ranks.values()):
            return {}

        averaged = {
            player_key: sum(ranks) / len(ranks)
            for player_key, ranks in daily_ranks.items()
            if ranks
        }
        sorted_players = sorted(averaged.items(), key=lambda item: item[1])
        return {player_key: rank for rank, (player_key, _) in enumerate(sorted_players, start=1)}


def parse_roster_xml(xml_text: str) -> RosterSnapshot:
    root = ET.fromstring(xml_text)
    team = first_descendant(root, "team")
    roster = first_descendant(team, "roster") if team is not None else None

    team_key = find_child_text(team, "team_key", default="") if team is not None else ""
    team_name = find_child_text(team, "name") if team is not None else None
    lineup_date = find_child_text(roster, "date") if roster is not None else None
    coverage_type = find_child_text(roster, "coverage_type") if roster is not None else None

    players_parent = first_descendant(roster, "players") if roster is not None else None
    players = []
    if players_parent is not None:
        for player_node in list(players_parent):
            if local_name(player_node.tag) != "player":
                continue
            players.append(parse_player(player_node))

    return RosterSnapshot(
        team_key=team_key,
        team_name=team_name,
        lineup_date=lineup_date,
        coverage_type=coverage_type,
        players=players,
        league_profile_key=None,
        slot_limits=DEFAULT_SLOT_LIMITS.copy(),
    )


def parse_player(player_node: ET.Element) -> Player:
    player_key = find_child_text(player_node, "player_key", default="")
    player_id = find_child_text(player_node, "player_id", default="")
    name_node = first_descendant(player_node, "name")
    full_name = find_child_text(name_node, "full", default="Unknown Player")
    display_position = find_child_text(player_node, "display_position")
    editorial_team_abbr = find_child_text(player_node, "editorial_team_abbr")
    editorial_team_full_name = find_child_text(player_node, "editorial_team_full_name")
    primary_position = find_child_text(player_node, "primary_position")
    status = find_child_text(player_node, "status")
    position_type = find_child_text(player_node, "position_type")
    image_url = find_child_text(first_descendant(player_node, "headshot"), "url") or find_child_text(player_node, "image_url")
    yahoo_o_rank = parse_yahoo_o_rank(player_node)
    selected_position_node = first_descendant(player_node, "selected_position")
    selected_position = find_child_text(selected_position_node, "position")
    eligible_positions_node = first_descendant(player_node, "eligible_positions")
    eligible_positions = tuple(
        (child.text or "").strip()
        for child in list(eligible_positions_node or [])
        if local_name(child.tag) == "position" and (child.text or "").strip()
    )

    is_locked = parse_player_lock(player_node)
    is_starting_today = parse_starting_status(player_node)
    game_start_time = (
        find_child_text(first_descendant(player_node, "starting_status"), "starting_date")
        or find_child_text(first_descendant(player_node, "game"), "start_time")
    )

    return Player(
        player_key=player_key,
        player_id=player_id,
        name=full_name,
        editorial_team_abbr=editorial_team_abbr,
        editorial_team_full_name=editorial_team_full_name,
        display_position=display_position,
        primary_position=primary_position,
        eligible_positions=eligible_positions,
        selected_position=selected_position,
        status=status,
        position_type=position_type,
        yahoo_o_rank=yahoo_o_rank,
        yahoo_average_pick=None,
        yahoo_actual_rank_last_week=None,
        yahoo_percent_started=None,
        yahoo_percent_owned=None,
        is_starting_today=is_starting_today,
        starting_status_reason=None,
        game_start_time=game_start_time,
        is_locked=is_locked,
        image_url=image_url,
    )


def parse_player_lock(player_node: ET.Element) -> bool:
    editable = find_descendant_text(player_node, "is_editable")
    if editable is not None:
        return editable == "0"
    return False


def parse_starting_status(player_node: ET.Element) -> bool | None:
    starting_status = find_descendant_text(player_node, "is_starting")
    if starting_status == "1":
        return True
    if starting_status == "0":
        return False

    starting_description = find_descendant_text(player_node, "starting_status")
    if starting_description:
        normalized = starting_description.strip().lower()
        if normalized in {"starting", "probable", "confirmed"}:
            return True
        if normalized in {"not starting", "out", "bench"}:
            return False
    return None


def parse_yahoo_o_rank(player_node: ET.Element) -> int | None:
    # Yahoo roster payloads vary across resources, so accept a few candidate rank fields.
    for field_name in ("rank", "overall_rank", "player_rank"):
        raw_value = find_descendant_text(player_node, field_name)
        if raw_value and raw_value.isdigit():
            return int(raw_value)
    return None


def parse_metric_value(xml_text: str, metric_name: str) -> int | None:
    root = ET.fromstring(xml_text)
    metric_node = first_descendant(root, metric_name)
    if metric_node is None:
        return None
    value = find_child_text(metric_node, "value")
    if value and value.isdigit():
        return int(value)
    return None


def parse_average_pick(xml_text: str) -> float | None:
    root = ET.fromstring(xml_text)
    draft_analysis_node = first_descendant(root, "draft_analysis")
    if draft_analysis_node is None:
        return None
    value = find_child_text(draft_analysis_node, "average_pick")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_player_order_map(xml_text: str) -> dict[str, int]:
    root = ET.fromstring(xml_text)
    players_parent = first_descendant(root, "players")
    if players_parent is None:
        return {}

    ordered_keys: dict[str, int] = {}
    rank = 1
    for player_node in list(players_parent):
        if local_name(player_node.tag) != "player":
            continue
        player_key = find_child_text(player_node, "player_key")
        if not player_key:
            continue
        ordered_keys[player_key] = rank
        rank += 1
    return ordered_keys


def parse_league_stat_categories(xml_text: str) -> dict[str, dict]:
    root = ET.fromstring(xml_text)
    stat_categories_node = first_descendant(root, "stat_categories")
    stats_node = first_descendant(stat_categories_node, "stats")
    if stats_node is None:
        return {}

    categories: dict[str, dict] = {}
    for stat_node in list(stats_node):
        if local_name(stat_node.tag) != "stat":
            continue
        stat_id = find_child_text(stat_node, "stat_id")
        if not stat_id:
            continue
        categories[stat_id] = {
            "stat_id": stat_id,
            "name": find_child_text(stat_node, "name"),
            "display_name": find_child_text(stat_node, "display_name") or find_child_text(stat_node, "abbr") or stat_id,
            "abbr": find_child_text(stat_node, "abbr"),
            "group": find_child_text(stat_node, "group"),
            "sort_order": find_child_text(stat_node, "sort_order"),
            "enabled": find_child_text(stat_node, "enabled") == "1",
            "is_only_display_stat": find_child_text(stat_node, "is_only_display_stat") == "1",
        }
    return categories


def parse_league_roster_positions(xml_text: str) -> dict[str, int]:
    root = ET.fromstring(xml_text)
    roster_positions_node = first_descendant(root, "roster_positions")
    roster_position_nodes = [
        node
        for node in list(roster_positions_node or [])
        if local_name(node.tag) == "roster_position"
    ]

    if not roster_position_nodes:
        return {}

    slot_limits: dict[str, int] = {}
    for roster_position_node in roster_position_nodes:
        position = find_child_text(roster_position_node, "position")
        count = find_child_text(roster_position_node, "count")
        if not position:
            continue
        normalized = position.strip()
        if normalized in {"IL+", "IR"}:
            normalized = "IL"
        if normalized == "Util":
            normalized = "Util"
        try:
            slot_limits[normalized] = slot_limits.get(normalized, 0) + int(count or "1")
        except ValueError:
            slot_limits[normalized] = slot_limits.get(normalized, 0) + 1
    return slot_limits


def parse_current_matchup_xml(
    xml_text: str,
    my_team_key: str,
    stat_categories: dict[str, dict],
) -> MatchupSnapshot | None:
    root = ET.fromstring(xml_text)
    matchups_node = first_descendant(root, "matchups")
    if matchups_node is None:
        return None

    matchup_node = next((node for node in list(matchups_node) if local_name(node.tag) == "matchup"), None)
    if matchup_node is None:
        return None

    teams_node = first_descendant(matchup_node, "teams")
    if teams_node is None:
        return None

    team_nodes = [node for node in list(teams_node) if local_name(node.tag) == "team"]
    my_team_node = next((node for node in team_nodes if find_child_text(node, "team_key") == my_team_key), None)
    opponent_team_node = next((node for node in team_nodes if find_child_text(node, "team_key") != my_team_key), None)
    if my_team_node is None:
        return None

    stat_winners_node = first_descendant(matchup_node, "stat_winners")
    winner_map: dict[str, dict] = {}
    if stat_winners_node is not None:
        for stat_winner_node in list(stat_winners_node):
            if local_name(stat_winner_node.tag) != "stat_winner":
                continue
            stat_id = find_child_text(stat_winner_node, "stat_id")
            if not stat_id:
                continue
            winner_map[stat_id] = {
                "winner_team_key": find_child_text(stat_winner_node, "winner_team_key"),
                "is_tied": find_child_text(stat_winner_node, "is_tied") == "1",
            }

    my_stats = parse_team_stats(my_team_node)
    opponent_stats = parse_team_stats(opponent_team_node) if opponent_team_node is not None else {}

    categories: list[MatchupCategory] = []
    stat_ids = sorted(
        {*(stat_categories.keys()), *(my_stats.keys()), *(opponent_stats.keys()), *(winner_map.keys())},
        key=lambda stat_id: int(stat_id) if stat_id.isdigit() else stat_id,
    )
    for stat_id in stat_ids:
        category_info = stat_categories.get(stat_id, {})
        if category_info.get("is_only_display_stat"):
            continue
        category_key = matchup_category_key(category_info.get("group"), category_info.get("display_name") or stat_id)
        categories.append(
            MatchupCategory(
                stat_id=stat_id,
                category_key=category_key,
                display_name=category_info.get("display_name") or stat_id,
                group=category_info.get("group"),
                my_value=my_stats.get(stat_id),
                opponent_value=opponent_stats.get(stat_id),
                winner_team_key=winner_map.get(stat_id, {}).get("winner_team_key"),
                is_tied=winner_map.get(stat_id, {}).get("is_tied", False),
            )
        )

    return MatchupSnapshot(
        week=_parse_optional_int(find_child_text(matchup_node, "week")),
        week_start=find_child_text(matchup_node, "week_start"),
        week_end=find_child_text(matchup_node, "week_end"),
        status=find_child_text(matchup_node, "status"),
        team_key=my_team_key,
        team_name=find_child_text(my_team_node, "name"),
        opponent_team_key=find_child_text(opponent_team_node, "team_key") if opponent_team_node is not None else None,
        opponent_team_name=find_child_text(opponent_team_node, "name") if opponent_team_node is not None else None,
        team_points=_parse_optional_float(find_descendant_text(first_descendant(my_team_node, "team_points"), "total")),
        opponent_team_points=_parse_optional_float(find_descendant_text(first_descendant(opponent_team_node, "team_points"), "total")) if opponent_team_node is not None else None,
        categories=categories,
    )


def parse_team_stats(team_node: ET.Element | None) -> dict[str, str]:
    team_stats_node = first_descendant(team_node, "team_stats")
    stats_node = first_descendant(team_stats_node, "stats")
    if stats_node is None:
        return {}
    stats: dict[str, str] = {}
    for stat_node in list(stats_node):
        if local_name(stat_node.tag) != "stat":
            continue
        stat_id = find_child_text(stat_node, "stat_id")
        value = find_child_text(stat_node, "value")
        if stat_id:
            stats[stat_id] = value or ""
    return stats


def parse_numeric_stat_value(value: str | None) -> float | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized or normalized == "-":
        return None
    if "/" in normalized:
        return None
    try:
        return float(normalized)
    except ValueError:
        return None


def normalize_matchup_group(group: str | None) -> str:
    normalized = (group or "").strip().lower()
    if normalized in {"hitting", "batting", "batter"}:
        return "batting"
    if normalized in {"pitching", "pitcher"}:
        return "pitching"
    return normalized or "unknown"


def matchup_category_key(group: str | None, display_name: str) -> str:
    return f"{normalize_matchup_group(group)}:{display_name}"


def build_matchup_delta_map(matchup: MatchupSnapshot) -> dict[str, MatchupCategoryDelta]:
    delta_map: dict[str, MatchupCategoryDelta] = {}
    for category in matchup.categories:
        my_numeric_value = parse_numeric_stat_value(category.my_value)
        opponent_numeric_value = parse_numeric_stat_value(category.opponent_value)
        delta = None
        if my_numeric_value is not None and opponent_numeric_value is not None:
            delta = round(my_numeric_value - opponent_numeric_value, 3)
        delta_map[category.category_key] = MatchupCategoryDelta(
            stat_id=category.stat_id,
            category_key=category.category_key,
            display_name=category.display_name,
            group=category.group,
            my_raw_value=category.my_value,
            opponent_raw_value=category.opponent_value,
            my_numeric_value=my_numeric_value,
            opponent_numeric_value=opponent_numeric_value,
            delta=delta,
            winner_team_key=category.winner_team_key,
            is_tied=category.is_tied,
        )
    return delta_map


def _parse_optional_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_optional_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def build_roster_update_xml(lineup_date: str, moves: list[PlannedMove]) -> str:
    players_xml = "\n".join(
        [
            "      <player>\n"
            f"        <player_key>{move.player_key}</player_key>\n"
            f"        <position>{move.to_position}</position>\n"
            "      </player>"
            for move in moves
        ]
    )
    return (
        '<?xml version="1.0"?>\n'
        "<fantasy_content>\n"
        "  <roster>\n"
        "    <coverage_type>date</coverage_type>\n"
        f"    <date>{lineup_date}</date>\n"
        "    <players>\n"
        f"{players_xml}\n"
        "    </players>\n"
        "  </roster>\n"
        "</fantasy_content>\n"
    )


def first_descendant(element: ET.Element | None, child_name: str) -> ET.Element | None:
    if element is None:
        return None
    for child in element.iter():
        if local_name(child.tag) == child_name:
            return child
    return None


def find_descendant_text(element: ET.Element | None, child_name: str) -> str | None:
    child = first_descendant(element, child_name)
    if child is None or child.text is None:
        return None
    value = child.text.strip()
    return value or None
