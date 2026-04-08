from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Player:
    player_key: str
    player_id: str
    name: str
    editorial_team_abbr: str | None
    editorial_team_full_name: str | None
    display_position: str | None
    primary_position: str | None
    eligible_positions: tuple[str, ...]
    selected_position: str | None
    status: str | None = None
    position_type: str | None = None
    yahoo_o_rank: int | None = None
    yahoo_average_pick: float | None = None
    yahoo_actual_rank_last_week: int | None = None
    yahoo_percent_started: int | None = None
    yahoo_percent_owned: int | None = None
    is_starting_today: bool | None = None
    starting_status_reason: str | None = None
    game_start_time: str | None = None
    is_locked: bool = False
    image_url: str | None = None


@dataclass(frozen=True)
class PlannedMove:
    player_key: str
    player_name: str
    from_position: str | None
    to_position: str | None
    reason: str


@dataclass(frozen=True)
class LineupPlan:
    moves: list[PlannedMove] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.moves)


@dataclass(frozen=True)
class RosterSnapshot:
    team_key: str
    team_name: str | None
    lineup_date: str | None
    coverage_type: str | None
    players: list[Player]
    league_profile_key: str | None = None
    slot_limits: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class MatchupCategory:
    stat_id: str
    category_key: str
    display_name: str
    group: str | None
    my_value: str | None
    opponent_value: str | None
    winner_team_key: str | None
    is_tied: bool


@dataclass(frozen=True)
class MatchupCategoryDelta:
    stat_id: str
    category_key: str
    display_name: str
    group: str | None
    my_raw_value: str | None
    opponent_raw_value: str | None
    my_numeric_value: float | None
    opponent_numeric_value: float | None
    delta: float | None
    winner_team_key: str | None
    is_tied: bool


@dataclass(frozen=True)
class MatchupSnapshot:
    week: int | None
    week_start: str | None
    week_end: str | None
    status: str | None
    team_key: str
    team_name: str | None
    opponent_team_key: str | None
    opponent_team_name: str | None
    team_points: float | None
    opponent_team_points: float | None
    categories: list[MatchupCategory] = field(default_factory=list)
