from __future__ import annotations

from dataclasses import replace
import xml.etree.ElementTree as ET
from typing import Iterable

import requests

from auth import load_token_file, refresh_access_token, save_token_file
from config import AppConfig
from lineup import DEFAULT_SLOT_LIMITS
from models import PlannedMove, Player, RosterSnapshot
from utils import find_child_text, local_name

BASE_URL = "https://fantasysports.yahooapis.com/fantasy/v2"


class YahooFantasyClient:
    def __init__(self, config: AppConfig):
        self.config = config
        self.session = requests.Session()
        self._player_percent_started_cache: dict[str, int | None] = {}
        self._player_percent_owned_cache: dict[str, int | None] = {}
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
        return self._populate_player_yahoo_metrics(roster)

    def set_lineup(self, lineup_date: str, moves: Iterable[PlannedMove]) -> None:
        xml_body = build_roster_update_xml(lineup_date=lineup_date, moves=list(moves))
        response = self.session.put(
            f"{BASE_URL}/team/{self.config.yahoo_team_key}/roster",
            data=xml_body.encode("utf-8"),
            timeout=30,
        )
        response.raise_for_status()

    def _populate_player_yahoo_metrics(self, roster: RosterSnapshot) -> RosterSnapshot:
        players = []
        for player in roster.players:
            players.append(
                replace(
                    player,
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

    def _fetch_player_metric(self, player_key: str, resource: str) -> int | None:
        response = self.session.get(
            f"{BASE_URL}/player/{player_key}/{resource}",
            timeout=30,
        )
        if response.status_code >= 400:
            return None
        return parse_metric_value(response.text, resource)


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
