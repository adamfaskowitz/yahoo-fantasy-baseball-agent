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
    slot_limits: dict[str, int] = field(default_factory=dict)
