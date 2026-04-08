from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

import requests

from league_profiles import get_league_profile
from mlb_lineups import find_player_mlb_person_id
from models import MatchupCategoryDelta, Player

MLB_BASE = "https://statsapi.mlb.com/api/v1"

ProjectionType = Literal["hitting", "pitching"]

NEGATIVE_CATEGORIES = {"batting:K", "pitching:ERA", "pitching:WHIP"}


@dataclass(frozen=True)
class PlayerProjection:
    player_key: str
    player_name: str
    projection_type: ProjectionType
    source_window: str
    stats: dict[str, float]
    details: dict[str, float]


def _season_start(target_date: date) -> date:
    # Good enough for MLB regular season fantasy usage.
    return date(target_date.year, 3, 1)


def _parse_rate(value: str | None) -> float:
    if not value or value == "-.--":
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def _parse_int(value) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _fetch_stat_line(
    person_id: str,
    *,
    group: ProjectionType,
    stats: str,
    target_date: date,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, float]:
    params = {
        "stats": stats,
        "group": group,
        "sportIds": 1,
    }
    if start_date is not None:
        params["startDate"] = start_date.isoformat()
    if end_date is not None:
        params["endDate"] = end_date.isoformat()
    if stats == "season":
        params["season"] = str(target_date.year)

    response = requests.get(
        f"{MLB_BASE}/people/{person_id}/stats",
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    stat_blocks = payload.get("stats") or []
    if not stat_blocks:
        return {}
    splits = stat_blocks[0].get("splits") or []
    if not splits:
        return {}
    return splits[0].get("stat") or {}


def _blended_rate(last30: float, season: float, *, recent_weight: float = 0.7) -> float:
    return recent_weight * last30 + (1.0 - recent_weight) * season


def _safe_divide(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _hitter_projection_from_lines(
    player: Player,
    *,
    last30: dict[str, float],
    season: dict[str, float],
    league_profile_key: str | None,
) -> PlayerProjection:
    last30_games = max(_parse_int(last30.get("gamesPlayed")), 1)
    season_games = max(_parse_int(season.get("gamesPlayed")), 1)
    last30_at_bats = max(_parse_int(last30.get("atBats")), 1)
    season_at_bats = max(_parse_int(season.get("atBats")), 1)

    rates_last30 = {
        "R": _safe_divide(_parse_int(last30.get("runs")), last30_games),
        "H": _safe_divide(_parse_int(last30.get("hits")), last30_games),
        "HR": _safe_divide(_parse_int(last30.get("homeRuns")), last30_games),
        "RBI": _safe_divide(_parse_int(last30.get("rbi")), last30_games),
        "SB": _safe_divide(_parse_int(last30.get("stolenBases")), last30_games),
        "K": _safe_divide(_parse_int(last30.get("strikeOuts")), last30_games),
        "OPS": _parse_rate(last30.get("ops")),
        "AVG": _parse_rate(last30.get("avg")) or _safe_divide(_parse_int(last30.get("hits")), last30_at_bats),
    }
    rates_season = {
        "R": _safe_divide(_parse_int(season.get("runs")), season_games),
        "H": _safe_divide(_parse_int(season.get("hits")), season_games),
        "HR": _safe_divide(_parse_int(season.get("homeRuns")), season_games),
        "RBI": _safe_divide(_parse_int(season.get("rbi")), season_games),
        "SB": _safe_divide(_parse_int(season.get("stolenBases")), season_games),
        "K": _safe_divide(_parse_int(season.get("strikeOuts")), season_games),
        "OPS": _parse_rate(season.get("ops")),
        "AVG": _parse_rate(season.get("avg")) or _safe_divide(_parse_int(season.get("hits")), season_at_bats),
    }

    blended_all = {
        category: round(_blended_rate(rates_last30[category], rates_season[category]), 3)
        for category in ("R", "H", "HR", "RBI", "SB", "K", "OPS", "AVG")
    }
    profile = get_league_profile(league_profile_key)
    blended = {
        category: blended_all[category]
        for category in profile.hitting_categories
        if category in blended_all
    }
    return PlayerProjection(
        player_key=player.player_key,
        player_name=player.name,
        projection_type="hitting",
        source_window="70% last 30 days / 30% season per game",
        stats=blended,
        details={
            "last30_games": float(last30_games),
            "season_games": float(season_games),
            "last30_ops": rates_last30["OPS"],
            "season_ops": rates_season["OPS"],
            "last30_avg": rates_last30["AVG"],
            "season_avg": rates_season["AVG"],
        },
    )


def _pitcher_projection_from_lines(
    player: Player,
    *,
    last30: dict[str, float],
    season: dict[str, float],
    league_profile_key: str | None,
) -> PlayerProjection:
    last30_games = max(_parse_int(last30.get("gamesPlayed")), 1)
    season_games = max(_parse_int(season.get("gamesPlayed")), 1)
    last30_innings = max(_parse_rate(last30.get("inningsPitched")), 1.0)
    season_innings = max(_parse_rate(season.get("inningsPitched")), 1.0)

    rates_last30 = {
        "SV": _safe_divide(_parse_int(last30.get("saves")), last30_games),
        "HLD": _safe_divide(_parse_int(last30.get("holds")), last30_games),
        "SV+H": _safe_divide(_parse_int(last30.get("saves")) + _parse_int(last30.get("holds")), last30_games),
        "W": _safe_divide(_parse_int(last30.get("wins")), last30_games),
        "K": _safe_divide(_parse_int(last30.get("strikeOuts")), last30_games),
        "ERA": _parse_rate(last30.get("era")),
        "WHIP": _parse_rate(last30.get("whip")),
        "K/BB": _safe_divide(_parse_int(last30.get("strikeOuts")), max(_parse_int(last30.get("baseOnBalls")), 1)),
        "WIN%": _safe_divide(_parse_int(last30.get("wins")), max(_parse_int(last30.get("decisions")), 1)),
        "QS": _safe_divide(_parse_int(last30.get("qualityStarts")), last30_games),
    }
    rates_season = {
        "SV": _safe_divide(_parse_int(season.get("saves")), season_games),
        "HLD": _safe_divide(_parse_int(season.get("holds")), season_games),
        "SV+H": _safe_divide(_parse_int(season.get("saves")) + _parse_int(season.get("holds")), season_games),
        "W": _safe_divide(_parse_int(season.get("wins")), season_games),
        "K": _safe_divide(_parse_int(season.get("strikeOuts")), season_games),
        "ERA": _parse_rate(season.get("era")),
        "WHIP": _parse_rate(season.get("whip")),
        "K/BB": _safe_divide(_parse_int(season.get("strikeOuts")), max(_parse_int(season.get("baseOnBalls")), 1)),
        "WIN%": _safe_divide(_parse_int(season.get("wins")), max(_parse_int(season.get("decisions")), 1)),
        "QS": _safe_divide(_parse_int(season.get("qualityStarts")), season_games),
    }

    blended_all = {
        category: round(_blended_rate(rates_last30[category], rates_season[category]), 3)
        for category in ("SV", "HLD", "SV+H", "W", "K", "ERA", "WHIP", "K/BB", "WIN%", "QS")
    }
    profile = get_league_profile(league_profile_key)
    blended = {
        category: blended_all[category]
        for category in profile.pitching_categories
        if category in blended_all
    }
    return PlayerProjection(
        player_key=player.player_key,
        player_name=player.name,
        projection_type="pitching",
        source_window="70% last 30 days / 30% season per appearance",
        stats=blended,
        details={
            "last30_games": float(last30_games),
            "season_games": float(season_games),
            "last30_ip": float(last30_innings),
            "season_ip": float(season_innings),
        },
    )


def project_player_for_league_categories(
    player: Player,
    target_date: date,
    *,
    league_profile_key: str | None = None,
    verbose: bool = False,
) -> PlayerProjection | None:
    mlb_person_id = find_player_mlb_person_id(player, target_date.isoformat(), verbose=verbose)
    if mlb_person_id is None:
        return None

    projection_type: ProjectionType = "pitching" if (player.position_type or "").upper() == "P" else "hitting"
    last30_start = target_date - timedelta(days=30)
    season_start = _season_start(target_date)

    last30 = _fetch_stat_line(
        mlb_person_id,
        group=projection_type,
        stats="byDateRange",
        target_date=target_date,
        start_date=last30_start,
        end_date=target_date,
    )
    season = _fetch_stat_line(
        mlb_person_id,
        group=projection_type,
        stats="byDateRange",
        target_date=target_date,
        start_date=season_start,
        end_date=target_date,
    )

    if projection_type == "pitching":
        return _pitcher_projection_from_lines(
            player,
            last30=last30,
            season=season,
            league_profile_key=league_profile_key,
        )
    return _hitter_projection_from_lines(
        player,
        last30=last30,
        season=season,
        league_profile_key=league_profile_key,
    )


def matchup_day_factor(target_date: date) -> float:
    # Monday=0 ... Sunday=6
    weekday = target_date.weekday()
    if weekday <= 2:
        return 0.0
    if weekday == 3:
        return 0.25
    if weekday == 4:
        return 0.45
    if weekday == 5:
        return 0.7
    return 1.0


def category_urgency_weights(
    category_deltas: dict[str, float],
    *,
    close_gap: float = 1.0,
    medium_gap: float = 3.0,
) -> dict[str, float]:
    weights: dict[str, float] = {}
    for category, delta in category_deltas.items():
        gap = abs(delta)
        if gap <= close_gap:
            weights[category] = 1.0
        elif gap <= medium_gap:
            weights[category] = 0.5
        else:
            weights[category] = 0.15
    return weights


def projection_category_key(projection_type: ProjectionType, category: str) -> str:
    group = "pitching" if projection_type == "pitching" else "batting"
    return f"{group}:{category}"


def weighted_matchup_score(
    projection: PlayerProjection,
    urgency_weights: dict[str, float],
    *,
    league_profile_key: str | None = None,
) -> float:
    profile = get_league_profile(league_profile_key)
    negative_categories = profile.negative_categories or NEGATIVE_CATEGORIES
    score = 0.0
    for category, value in projection.stats.items():
        category_key = projection_category_key(projection.projection_type, category)
        weight = urgency_weights.get(category_key, 0.0)
        if weight == 0.0:
            continue
        contribution = -value if category_key in negative_categories else value
        score += contribution * weight
    return round(score, 3)


def batting_category_deltas(delta_map: dict[str, MatchupCategoryDelta]) -> dict[str, float]:
    return {
        category_key: category.delta
        for category_key, category in delta_map.items()
        if category_key.startswith("batting:") and category.delta is not None
    }


def build_hitter_matchup_adjustments(
    players: list[Player],
    target_date: date,
    delta_map: dict[str, MatchupCategoryDelta],
    *,
    league_profile_key: str | None = None,
    multiplier: float = 25.0,
    verbose: bool = False,
) -> dict[str, int]:
    profile = get_league_profile(league_profile_key)
    if not profile.matchup_enabled:
        return {}
    day_factor = matchup_day_factor(target_date)
    if day_factor <= 0:
        return {}

    batting_deltas = batting_category_deltas(delta_map)
    if not batting_deltas:
        return {}

    urgency = category_urgency_weights(batting_deltas)
    adjustments: dict[str, int] = {}
    for player in players:
        if (player.position_type or "").upper() != "B":
            continue
        projection = project_player_for_league_categories(
            player,
            target_date,
            league_profile_key=league_profile_key,
            verbose=verbose,
        )
        if projection is None or projection.projection_type != "hitting":
            continue
        raw_score = weighted_matchup_score(
            projection,
            urgency,
            league_profile_key=league_profile_key,
        )
        adjustments[player.player_key] = int(round(raw_score * day_factor * multiplier))
    return adjustments
