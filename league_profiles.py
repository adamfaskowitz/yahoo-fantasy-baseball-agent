from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LeagueProfile:
    key: str
    name: str
    scoring_mode: str
    active_slot_order: tuple[str, ...]
    render_groups: tuple[str, ...]
    hitting_categories: tuple[str, ...]
    pitching_categories: tuple[str, ...]
    negative_categories: frozenset[str]
    matchup_enabled: bool


H2H_CATEGORIES_PROFILE = LeagueProfile(
    key="h2h_categories",
    name="H2H Categories",
    scoring_mode="h2h_categories",
    active_slot_order=("C", "1B", "2B", "3B", "SS", "IF", "LF", "CF", "RF", "OF", "Util", "SP", "RP", "P"),
    render_groups=(
        "C",
        "1B",
        "2B",
        "3B",
        "SS",
        "IF",
        "LF",
        "CF",
        "RF",
        "OF",
        "UTIL",
        "BN_B",
        "IL_B",
        "NA_B",
        "SP",
        "RP",
        "P",
        "BN_P",
        "IL_P",
        "NA_P",
    ),
    hitting_categories=("R", "H", "HR", "RBI", "SB", "K", "OPS"),
    pitching_categories=("SV", "K", "ERA", "WHIP", "K/BB", "WIN%", "QS"),
    negative_categories=frozenset({"batting:K", "pitching:ERA", "pitching:WHIP"}),
    matchup_enabled=True,
)


ROTO_5X5_DYNASTY_PROFILE = LeagueProfile(
    key="roto_5x5_dynasty",
    name="Roto 5x5 Dynasty",
    scoring_mode="roto_categories",
    active_slot_order=("C", "1B", "2B", "3B", "SS", "CI", "MI", "OF", "Util", "P"),
    render_groups=(
        "C",
        "1B",
        "2B",
        "3B",
        "SS",
        "CI",
        "MI",
        "OF",
        "UTIL",
        "BN_B",
        "IL_B",
        "NA_B",
        "P",
        "BN_P",
        "IL_P",
        "NA_P",
    ),
    hitting_categories=("R", "HR", "RBI", "SB", "AVG"),
    pitching_categories=("W", "K", "ERA", "WHIP", "SV+H"),
    negative_categories=frozenset({"pitching:ERA", "pitching:WHIP"}),
    matchup_enabled=False,
)


LEAGUE_PROFILES = {
    H2H_CATEGORIES_PROFILE.key: H2H_CATEGORIES_PROFILE,
    ROTO_5X5_DYNASTY_PROFILE.key: ROTO_5X5_DYNASTY_PROFILE,
}

LEAGUE_ID_TO_PROFILE_KEY = {
    "106459": H2H_CATEGORIES_PROFILE.key,
    "174916": ROTO_5X5_DYNASTY_PROFILE.key,
}


def league_id_from_team_key(team_key: str | None) -> str | None:
    if not team_key:
        return None
    parts = team_key.split(".")
    if len(parts) != 5 or parts[1] != "l":
        return None
    return parts[2]


def default_profile_key_for_team_key(team_key: str | None) -> str:
    league_id = league_id_from_team_key(team_key)
    if league_id and league_id in LEAGUE_ID_TO_PROFILE_KEY:
        return LEAGUE_ID_TO_PROFILE_KEY[league_id]
    return H2H_CATEGORIES_PROFILE.key


def get_league_profile(profile_key: str | None) -> LeagueProfile:
    if profile_key and profile_key in LEAGUE_PROFILES:
        return LEAGUE_PROFILES[profile_key]
    return H2H_CATEGORIES_PROFILE
