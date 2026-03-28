from __future__ import annotations

from dataclasses import dataclass, replace

from lineup import DEFAULT_SLOT_LIMITS, apply_plan_to_roster, optimize_lineup
from models import Player, RosterSnapshot


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    roster: RosterSnapshot
    expected_moves: tuple[str, ...]
    expected_warnings: tuple[str, ...] = ()


def player(
    player_id: str,
    name: str,
    slot: str,
    eligible: tuple[str, ...],
    *,
    team_abbr: str = "LAD",
    team_name: str = "Los Angeles Dodgers",
    display_position: str | None = None,
    primary_position: str | None = None,
    position_type: str | None = None,
    yahoo_o_rank: int | None = None,
    yahoo_percent_started: int | None = None,
    yahoo_percent_owned: int | None = None,
    is_starting_today: bool | None = None,
    starting_status_reason: str | None = None,
    is_locked: bool = False,
    status: str | None = None,
) -> Player:
    display = display_position or ",".join(eligible)
    primary = primary_position or eligible[0]
    if position_type is None:
        position_type = "P" if {"SP", "RP", "P"} & set(eligible) else "B"
    return Player(
        player_key=f"458.p.{player_id}",
        player_id=player_id,
        name=name,
        editorial_team_abbr=team_abbr,
        editorial_team_full_name=team_name,
        display_position=display,
        primary_position=primary,
        eligible_positions=eligible,
        selected_position=slot,
        status=status,
        position_type=position_type,
        yahoo_o_rank=yahoo_o_rank,
        yahoo_percent_started=yahoo_percent_started,
        yahoo_percent_owned=yahoo_percent_owned,
        is_starting_today=is_starting_today,
        starting_status_reason=starting_status_reason,
        is_locked=is_locked,
    )


def base_roster() -> RosterSnapshot:
    players = [
        player("11268", "William Contreras", "C", ("C", "Util"), team_abbr="MIL", team_name="Milwaukee Brewers", is_starting_today=False, starting_status_reason="not_starting"),
        player("11125", "Brandon Lowe", "1B", ("1B", "2B", "IF", "Util"), team_abbr="PIT", team_name="Pittsburgh Pirates", is_starting_today=None, starting_status_reason="player_unmapped"),
        player("10236", "Gleyber Torres", "2B", ("2B", "IF", "Util"), team_abbr="DET", team_name="Detroit Tigers", is_starting_today=False, starting_status_reason="not_starting"),
        player("10922", "Mark Vientos", "3B", ("3B", "IF", "Util"), team_abbr="NYM", team_name="New York Mets", is_starting_today=True, starting_status_reason="starting"),
        player("9116", "Francisco Lindor", "SS", ("SS", "IF", "Util"), team_abbr="NYM", team_name="New York Mets", is_starting_today=True, starting_status_reason="starting"),
        player("12393", "Elly De La Cruz", "IF", ("SS", "IF", "Util"), team_abbr="CIN", team_name="Cincinnati Reds", is_starting_today=True, starting_status_reason="starting"),
        player("9339", "George Springer", "LF", ("LF", "CF", "RF", "OF", "Util"), team_abbr="TOR", team_name="Toronto Blue Jays", is_starting_today=True, starting_status_reason="starting"),
        player("62973", "Wyatt Langford", "CF", ("LF", "CF", "OF", "Util"), team_abbr="TEX", team_name="Texas Rangers", is_starting_today=None, starting_status_reason="player_unmapped"),
        player("12480", "Jackson Chourio", "RF", ("LF", "CF", "RF", "OF", "Util"), team_abbr="MIL", team_name="Milwaukee Brewers", is_starting_today=True, starting_status_reason="starting"),
        player("12136", "Brenton Doyle", "OF", ("CF", "OF", "Util"), team_abbr="COL", team_name="Colorado Rockies", is_starting_today=True, starting_status_reason="starting"),
        player("1000001", "Shohei Ohtani (Batter)", "Util", ("Util",), team_abbr="LAD", team_name="Los Angeles Dodgers", display_position="Util", primary_position="Util", is_starting_today=None, starting_status_reason="player_unmapped"),
        player("10893", "Jo Adell", "BN", ("CF", "RF", "OF", "Util"), team_abbr="LAA", team_name="Los Angeles Angels", is_starting_today=True, starting_status_reason="starting"),
        player("12122", "Jordan Westburg", "BN", ("2B", "3B", "IF", "Util"), team_abbr="BAL", team_name="Baltimore Orioles", display_position="2B,3B", primary_position="2B", is_starting_today=True, starting_status_reason="starting"),
        player("12141", "Hunter Brown", "SP", ("SP", "P"), team_abbr="HOU", team_name="Houston Astros", is_starting_today=False, starting_status_reason="not_starting", position_type="P"),
        player("9701", "Jacob deGrom", "SP", ("SP", "P"), team_abbr="TEX", team_name="Texas Rangers", is_starting_today=False, starting_status_reason="not_starting", position_type="P"),
        player("60042", "Parker Messick", "SP", ("SP", "P"), team_abbr="CLE", team_name="Cleveland Guardians", is_starting_today=False, starting_status_reason="not_starting", position_type="P"),
        player("11628", "Devin Williams", "RP", ("RP", "P"), team_abbr="NYM", team_name="New York Mets", is_starting_today=None, starting_status_reason="reliever", position_type="P"),
        player("10901", "Dennis Santana", "RP", ("RP", "P"), team_abbr="PIT", team_name="Pittsburgh Pirates", is_starting_today=None, starting_status_reason="reliever", position_type="P"),
        player("64978", "Jonah Tong", "P", ("SP", "P", "NA"), team_abbr="NYM", team_name="New York Mets", is_starting_today=False, starting_status_reason="not_starting", position_type="P", status="NA"),
        player("60121", "Daniel Palencia", "P", ("RP", "P"), team_abbr="CHC", team_name="Chicago Cubs", is_starting_today=None, starting_status_reason="reliever", position_type="P"),
        player("10730", "Brandon Woodruff", "P", ("SP", "P"), team_abbr="MIL", team_name="Milwaukee Brewers", is_starting_today=None, starting_status_reason="player_unmapped", position_type="P"),
        player("11014", "Freddy Peralta", "BN", ("SP", "P"), team_abbr="MIL", team_name="Milwaukee Brewers", is_starting_today=None, starting_status_reason="player_unmapped", position_type="P"),
        player("9334", "Kevin Gausman", "BN", ("SP", "P"), team_abbr="TOR", team_name="Toronto Blue Jays", is_starting_today=True, starting_status_reason="starting", position_type="P"),
        player("11057", "Pablo Lopez", "BN", ("SP", "P"), team_abbr="MIN", team_name="Minnesota Twins", display_position="SP", primary_position="SP", is_starting_today=None, starting_status_reason="player_unmapped", position_type="P"),
        player("12346", "Felix Bautista", "BN", ("RP", "P"), team_abbr="BAL", team_name="Baltimore Orioles", display_position="RP", primary_position="RP", is_starting_today=None, starting_status_reason="reliever", position_type="P"),
        player("60214", "Zach Neto", "IL", ("SS", "IF", "Util"), team_abbr="LAA", team_name="Los Angeles Angels", is_starting_today=None, starting_status_reason="inactive_slot", status="DTD"),
        player("12721", "Warming Bernabel", "IL", ("1B", "3B", "IF", "Util", "NA"), team_abbr="WSH", team_name="Washington Nationals", display_position="1B,3B", primary_position="1B", is_starting_today=None, starting_status_reason="inactive_slot", status="NA"),
        player("11625", "Emmanuel Clase", "NA", ("RP", "P", "NA"), team_abbr="CLE", team_name="Cleveland Guardians", display_position="RP", primary_position="RP", is_starting_today=None, starting_status_reason="inactive_slot", position_type="P", status="NA"),
    ]
    return RosterSnapshot(
        team_key="458.l.62268.t.5",
        team_name="deGrom Reapers",
        lineup_date="2025-09-28",
        coverage_type="date",
        players=players,
        slot_limits=DEFAULT_SLOT_LIMITS.copy(),
    )


def roster_with_updates(
    roster: RosterSnapshot,
    updates: dict[str, dict],
) -> RosterSnapshot:
    players = []
    for current in roster.players:
        change = updates.get(current.name)
        players.append(replace(current, **change) if change else current)
    return replace(roster, players=players)


def expected_signature(plan) -> tuple[str, ...]:
    return tuple(f"{move.player_name}:{move.from_position}->{move.to_position}" for move in plan.moves)


def scenario_catalog() -> list[Scenario]:
    roster = base_roster()
    cases = [
        Scenario(
            name="baseline",
            description="Historical-style roster with the default conservative swaps.",
            roster=roster,
            expected_moves=(
                "Gleyber Torres:2B->BN",
                "Jordan Westburg:BN->2B",
                "Hunter Brown:SP->BN",
                "Kevin Gausman:BN->SP",
                "Jonah Tong:P->BN",
                "Felix Bautista:BN->P",
            ),
            expected_warnings=(
                "No eligible starting replacement found for William Contreras at C.",
                "No eligible starting replacement found for Jacob deGrom at SP.",
                "No eligible starting replacement found for Parker Messick at SP.",
            ),
        ),
        Scenario(
            name="cf_no_game_jo_adell",
            description="A no-game center fielder should be swapped for Jo Adell.",
            roster=roster_with_updates(roster, {"Wyatt Langford": {"starting_status_reason": "no_game"}}),
            expected_moves=(
                "Gleyber Torres:2B->BN",
                "Jordan Westburg:BN->2B",
                "Wyatt Langford:CF->BN",
                "Jo Adell:BN->CF",
                "Hunter Brown:SP->BN",
                "Kevin Gausman:BN->SP",
                "Jonah Tong:P->BN",
                "Felix Bautista:BN->P",
            ),
            expected_warnings=(
                "No eligible starting replacement found for William Contreras at C.",
                "No eligible starting replacement found for Jacob deGrom at SP.",
                "No eligible starting replacement found for Parker Messick at SP.",
            ),
        ),
        Scenario(
            name="no_game_can_use_lineup_pending_bench",
            description="A no-game active hitter can be replaced by an eligible lineup-pending bench hitter.",
            roster=roster_with_updates(
                roster,
                {
                    "Brandon Lowe": {"selected_position": "BN", "is_starting_today": None, "starting_status_reason": "lineup_pending"},
                    "Gleyber Torres": {"selected_position": "2B", "is_starting_today": None, "starting_status_reason": "no_game"},
                    "Jordan Westburg": {"selected_position": "BN", "is_starting_today": None, "starting_status_reason": "lineup_pending"},
                    "Hunter Brown": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Jacob deGrom": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Parker Messick": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Jonah Tong": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Kevin Gausman": {"is_starting_today": False, "starting_status_reason": "not_starting"},
                    "Felix Bautista": {"starting_status_reason": "inactive_slot"},
                },
            ),
            expected_moves=("Gleyber Torres:2B->BN", "Jordan Westburg:BN->2B"),
            expected_warnings=("No eligible starting replacement found for William Contreras at C.",),
        ),
        Scenario(
            name="no_game_vs_lineup_pending_only",
            description="Lineup-pending should still beat no-game even when no players are confirmed starting yet.",
            roster=replace(
                roster,
                players=[
                    player("1", "No Game 2B", "2B", ("2B",), is_starting_today=None, starting_status_reason="no_game"),
                    player("2", "Pending 2B", "BN", ("2B",), is_starting_today=None, starting_status_reason="lineup_pending"),
                ],
            ),
            expected_moves=("No Game 2B:2B->BN", "Pending 2B:BN->2B"),
            expected_warnings=(),
        ),
        Scenario(
            name="of_not_starting_jo_adell",
            description="A non-starting OF should be replaced by the bench OF bat.",
            roster=roster_with_updates(roster, {"Brenton Doyle": {"is_starting_today": False, "starting_status_reason": "not_starting"}}),
            expected_moves=(
                "Gleyber Torres:2B->BN",
                "Jordan Westburg:BN->2B",
                "Brenton Doyle:OF->BN",
                "Jo Adell:BN->OF",
                "Hunter Brown:SP->BN",
                "Kevin Gausman:BN->SP",
                "Jonah Tong:P->BN",
                "Felix Bautista:BN->P",
            ),
            expected_warnings=(
                "No eligible starting replacement found for William Contreras at C.",
                "No eligible starting replacement found for Jacob deGrom at SP.",
                "No eligible starting replacement found for Parker Messick at SP.",
            ),
        ),
        Scenario(
            name="o_rank_star_upgrade",
            description="A higher-ranked star on the bench should replace a lower-ranked starter even when both are starting.",
            roster=roster_with_updates(
                roster,
                {
                    "William Contreras": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Gleyber Torres": {"selected_position": "IF", "is_starting_today": True, "starting_status_reason": "starting"},
                    "Francisco Lindor": {"selected_position": "SS", "is_starting_today": True, "starting_status_reason": "starting", "yahoo_o_rank": 42},
                    "Elly De La Cruz": {"selected_position": "BN", "is_starting_today": True, "starting_status_reason": "starting", "yahoo_o_rank": 5},
                    "Jordan Westburg": {"selected_position": "2B", "is_starting_today": True, "starting_status_reason": "starting"},
                    "Hunter Brown": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Jacob deGrom": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Parker Messick": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Jonah Tong": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Jo Adell": {"is_starting_today": False, "starting_status_reason": "not_starting"},
                    "Kevin Gausman": {"is_starting_today": False, "starting_status_reason": "not_starting"},
                    "Felix Bautista": {"starting_status_reason": "inactive_slot"},
                },
            ),
            expected_moves=("Gleyber Torres:IF->BN", "Elly De La Cruz:BN->IF"),
        ),
        Scenario(
            name="catcher_warning_only",
            description="A non-starting catcher with no backup should only emit a warning.",
            roster=roster_with_updates(
                roster,
                {
                    "Gleyber Torres": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Hunter Brown": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Jacob deGrom": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Parker Messick": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Jonah Tong": {"is_starting_today": None, "starting_status_reason": "reliever"},
                    "Daniel Palencia": {"selected_position": "BN"},
                },
            ),
            expected_moves=("Felix Bautista:BN->RP", "Kevin Gausman:BN->P"),
            expected_warnings=("No eligible starting replacement found for William Contreras at C.",),
        ),
        Scenario(
            name="prefer_projection_for_2b",
            description="Projection should break ties between multiple eligible starting bench bats.",
            roster=roster_with_updates(
                roster,
                {
                    "Jordan Westburg": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Jo Adell": {"eligible_positions": ("2B", "Util"), "primary_position": "2B"},
                },
            ),
            expected_moves=(
                "Gleyber Torres:2B->BN",
                "Jo Adell:BN->2B",
                "Hunter Brown:SP->BN",
                "Kevin Gausman:BN->SP",
                "Jonah Tong:P->BN",
                "Felix Bautista:BN->P",
            ),
            expected_warnings=(
                "No eligible starting replacement found for William Contreras at C.",
                "No eligible starting replacement found for Jacob deGrom at SP.",
                "No eligible starting replacement found for Parker Messick at SP.",
            ),
        ),
        Scenario(
            name="locked_active_skipped",
            description="A locked non-starter should not be moved even if a replacement exists.",
            roster=roster_with_updates(roster, {"Gleyber Torres": {"is_locked": True}}),
            expected_moves=(
                "Hunter Brown:SP->BN",
                "Kevin Gausman:BN->SP",
                "Jonah Tong:P->BN",
                "Felix Bautista:BN->P",
            ),
            expected_warnings=(
                "No eligible starting replacement found for William Contreras at C.",
                "Gleyber Torres is locked at 2B; no change attempted.",
                "No eligible starting replacement found for Jacob deGrom at SP.",
                "No eligible starting replacement found for Parker Messick at SP.",
            ),
        ),
        Scenario(
            name="locked_bench_unavailable",
            description="A locked bench player should not be chosen as the replacement.",
            roster=roster_with_updates(roster, {"Jordan Westburg": {"is_locked": True}}),
            expected_moves=(
                "Hunter Brown:SP->BN",
                "Kevin Gausman:BN->SP",
                "Jonah Tong:P->BN",
                "Felix Bautista:BN->P",
            ),
            expected_warnings=(
                "No eligible starting replacement found for William Contreras at C.",
                "No eligible starting replacement found for Gleyber Torres at 2B.",
                "No eligible starting replacement found for Jacob deGrom at SP.",
                "No eligible starting replacement found for Parker Messick at SP.",
            ),
        ),
        Scenario(
            name="generic_p_prefers_reliever",
            description="A generic P slot should pick a reliever over an unmapped or non-starting SP.",
            roster=roster_with_updates(
                roster,
                {
                    "Jonah Tong": {"is_starting_today": False, "starting_status_reason": "not_starting"},
                    "Kevin Gausman": {"is_starting_today": False, "starting_status_reason": "not_starting"},
                    "Hunter Brown": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Jacob deGrom": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Parker Messick": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Gleyber Torres": {"is_starting_today": True, "starting_status_reason": "starting"},
                },
            ),
            expected_moves=("Jonah Tong:P->BN", "Felix Bautista:BN->P"),
            expected_warnings=("No eligible starting replacement found for William Contreras at C.",),
        ),
        Scenario(
            name="player_unmapped_conservative",
            description="An unmapped hitter should stay put if the optimizer cannot confirm the better move.",
            roster=roster_with_updates(roster, {"Wyatt Langford": {"starting_status_reason": "player_unmapped"}}),
            expected_moves=(
                "Gleyber Torres:2B->BN",
                "Jordan Westburg:BN->2B",
                "Hunter Brown:SP->BN",
                "Kevin Gausman:BN->SP",
                "Jonah Tong:P->BN",
                "Felix Bautista:BN->P",
            ),
            expected_warnings=(
                "No eligible starting replacement found for William Contreras at C.",
                "No eligible starting replacement found for Jacob deGrom at SP.",
                "No eligible starting replacement found for Parker Messick at SP.",
            ),
        ),
        Scenario(
            name="if_slot_uses_3b_eligible",
            description="The IF slot should accept a 3B-eligible bench bat.",
            roster=roster_with_updates(
                roster,
                {
                    "Elly De La Cruz": {"is_starting_today": False, "starting_status_reason": "not_starting"},
                    "Jordan Westburg": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Gleyber Torres": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Hunter Brown": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Jacob deGrom": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Parker Messick": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Jonah Tong": {"is_starting_today": True, "starting_status_reason": "starting"},
                },
            ),
            expected_moves=("Elly De La Cruz:IF->BN", "Jordan Westburg:BN->IF", "Felix Bautista:BN->RP"),
            expected_warnings=("No eligible starting replacement found for William Contreras at C.",),
        ),
        Scenario(
            name="util_accepts_batter",
            description="The Util slot should accept a starting hitter even without explicit Util eligibility logic issues.",
            roster=roster_with_updates(
                roster,
                {
                    "Shohei Ohtani (Batter)": {"starting_status_reason": "no_game"},
                    "Gleyber Torres": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Hunter Brown": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Jacob deGrom": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Parker Messick": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Jonah Tong": {"is_starting_today": True, "starting_status_reason": "starting"},
                },
            ),
            expected_moves=("Shohei Ohtani (Batter):Util->BN", "Jo Adell:BN->Util", "Felix Bautista:BN->RP"),
            expected_warnings=("No eligible starting replacement found for William Contreras at C.",),
        ),
        Scenario(
            name="single_bench_player_only_once",
            description="A single bench OF should only cover one open OF slot across repeated gaps.",
            roster=roster_with_updates(
                roster,
                {
                    "Wyatt Langford": {"starting_status_reason": "no_game"},
                    "Brenton Doyle": {"is_starting_today": False, "starting_status_reason": "not_starting"},
                    "Jordan Westburg": {"is_starting_today": False, "starting_status_reason": "not_starting"},
                },
            ),
            expected_moves=(
                "Wyatt Langford:CF->BN",
                "Jo Adell:BN->CF",
                "Hunter Brown:SP->BN",
                "Kevin Gausman:BN->SP",
                "Jonah Tong:P->BN",
                "Felix Bautista:BN->P",
            ),
            expected_warnings=(
                "No eligible starting replacement found for William Contreras at C.",
                "No eligible starting replacement found for Gleyber Torres at 2B.",
                "No eligible starting replacement found for Brenton Doyle at OF.",
                "No eligible starting replacement found for Jacob deGrom at SP.",
                "No eligible starting replacement found for Parker Messick at SP.",
            ),
        ),
        Scenario(
            name="all_unknown_guardrail",
            description="When every player is unknown, the optimizer should do nothing.",
            roster=replace(
                roster,
                players=[replace(current, is_starting_today=None, starting_status_reason="player_unmapped") for current in roster.players],
            ),
            expected_moves=(),
            expected_warnings=("No starting-status data is available yet. The optimizer will not move players blindly.",),
        ),
        Scenario(
            name="empty_roster",
            description="An empty roster should be handled cleanly.",
            roster=replace(roster, players=[]),
            expected_moves=(),
            expected_warnings=("Roster is empty.",),
        ),
        Scenario(
            name="apply_twice_idempotent",
            description="Once the plan is applied, the optimizer should not propose the same swaps again.",
            roster=apply_plan_to_roster(
                roster,
                optimize_lineup(roster),
            ),
            expected_moves=(),
            expected_warnings=(
                "No eligible starting replacement found for William Contreras at C.",
                "No eligible starting replacement found for Jacob deGrom at SP.",
                "No eligible starting replacement found for Parker Messick at SP.",
            ),
        ),
        Scenario(
            name="inactive_slot_not_used",
            description="IL and NA players should never be activated as bench replacements.",
            roster=roster_with_updates(
                roster,
                {
                    "Jo Adell": {"is_starting_today": False, "starting_status_reason": "not_starting"},
                    "Jordan Westburg": {"is_starting_today": False, "starting_status_reason": "not_starting"},
                    "Kevin Gausman": {"is_starting_today": False, "starting_status_reason": "not_starting"},
                    "Felix Bautista": {"starting_status_reason": "inactive_slot"},
                },
            ),
            expected_moves=(),
            expected_warnings=(
                "No eligible starting replacement found for William Contreras at C.",
                "No eligible starting replacement found for Gleyber Torres at 2B.",
                "No eligible starting replacement found for Hunter Brown at SP.",
                "No eligible starting replacement found for Jacob deGrom at SP.",
                "No eligible starting replacement found for Parker Messick at SP.",
                "No eligible starting replacement found for Jonah Tong at P.",
            ),
        ),
        Scenario(
            name="late_run_more_locked",
            description="A later run in the day should skip players that have become locked while still handling unlocked slots.",
            roster=roster_with_updates(
                roster,
                {
                    "Gleyber Torres": {"is_locked": True},
                    "Hunter Brown": {"is_locked": True},
                    "Jacob deGrom": {"is_locked": False},
                    "Jo Adell": {"is_locked": False},
                    "Jordan Westburg": {"is_locked": False},
                    "Kevin Gausman": {"is_locked": False},
                    "Felix Bautista": {"is_locked": False},
                },
            ),
            expected_moves=(
                "Jacob deGrom:SP->BN",
                "Kevin Gausman:BN->SP",
                "Jonah Tong:P->BN",
                "Felix Bautista:BN->P",
            ),
            expected_warnings=(
                "No eligible starting replacement found for William Contreras at C.",
                "Gleyber Torres is locked at 2B; no change attempted.",
                "Hunter Brown is locked at SP; no change attempted.",
                "No eligible starting replacement found for Parker Messick at SP.",
            ),
        ),
        Scenario(
            name="morning_run_lineup_pending",
            description="Morning runs should leave lineup-pending players untouched until a later pass.",
            roster=roster_with_updates(
                roster,
                {
                    "Gleyber Torres": {"is_starting_today": None, "starting_status_reason": "lineup_pending"},
                    "Hunter Brown": {"is_starting_today": None, "starting_status_reason": "lineup_pending"},
                    "Jonah Tong": {"is_starting_today": None, "starting_status_reason": "lineup_pending"},
                },
            ),
            expected_moves=("Jacob deGrom:SP->BN", "Kevin Gausman:BN->SP", "Felix Bautista:BN->RP"),
            expected_warnings=(
                "No eligible starting replacement found for William Contreras at C.",
                "No eligible starting replacement found for Parker Messick at SP.",
            ),
        ),
        Scenario(
            name="lineup_pending_percent_started_upgrade",
            description="A bench hitter with a stronger Yahoo % Start should replace a weaker lineup-pending active hitter.",
            roster=replace(
                roster,
                players=[
                    player("1", "Pending OF", "OF", ("CF", "OF"), is_starting_today=None, starting_status_reason="lineup_pending", yahoo_percent_started=18, yahoo_o_rank=1708),
                    player("2", "Pending CF", "CF", ("CF", "OF"), is_starting_today=None, starting_status_reason="lineup_pending", yahoo_percent_started=95, yahoo_o_rank=300),
                    player("3", "Bench Upgrade", "BN", ("CF", "OF"), is_starting_today=None, starting_status_reason="lineup_pending", yahoo_percent_started=89, yahoo_o_rank=42),
                ],
                slot_limits={"CF": 1, "OF": 1, "BN": 1},
            ),
            expected_moves=("Pending OF:OF->BN", "Bench Upgrade:BN->OF"),
            expected_warnings=(),
        ),
        Scenario(
            name="lineup_pending_middle_infield_percent_started_upgrade",
            description="A bench SS with better Yahoo % Start and O-Rank should replace a weaker pending SS directly.",
            roster=replace(
                roster,
                players=[
                    player("1", "Pending SS", "SS", ("SS", "IF"), is_starting_today=None, starting_status_reason="lineup_pending", yahoo_percent_started=40, yahoo_o_rank=125),
                    player("2", "Pending IF", "IF", ("2B", "IF"), is_starting_today=None, starting_status_reason="lineup_pending", yahoo_percent_started=84, yahoo_o_rank=18),
                    player("3", "Bench Star SS", "BN", ("SS", "IF"), is_starting_today=None, starting_status_reason="lineup_pending", yahoo_percent_started=99, yahoo_o_rank=5),
                ],
                slot_limits={"SS": 1, "IF": 1, "BN": 1},
            ),
            expected_moves=("Pending SS:SS->BN", "Bench Star SS:BN->SS"),
            expected_warnings=(),
        ),
        Scenario(
            name="confirmed_cf_prefers_cf_slot_for_flexibility",
            description="A confirmed CF should prefer CF over OF so the OF slot stays more flexible later.",
            roster=replace(
                roster,
                players=[
                    player("1", "Confirmed CF", "OF", ("CF", "OF"), is_starting_today=True, starting_status_reason="starting"),
                    player("2", "Pending OF", "CF", ("CF", "OF"), is_starting_today=None, starting_status_reason="lineup_pending", yahoo_percent_started=40),
                    player("3", "Bench LF", "BN", ("LF", "RF", "OF"), is_starting_today=None, starting_status_reason="lineup_pending", yahoo_percent_started=70),
                ],
                slot_limits={"CF": 1, "OF": 1, "BN": 1},
            ),
            expected_moves=("Pending OF:CF->BN", "Confirmed CF:OF->CF", "Bench LF:BN->OF"),
            expected_warnings=(),
        ),
        Scenario(
            name="confirmed_ss_prefers_ss_but_does_not_displace_star_if",
            description="A confirmed infielder should take SS over IF when quality is close, but should not bench a stronger pending star.",
            roster=replace(
                roster,
                players=[
                    player("1", "Confirmed SS", "IF", ("SS", "IF"), is_starting_today=True, starting_status_reason="starting", yahoo_o_rank=90),
                    player("2", "Pending Star SS", "SS", ("SS", "IF"), is_starting_today=None, starting_status_reason="lineup_pending", yahoo_percent_started=96, yahoo_o_rank=5),
                    player("3", "Confirmed 2B", "2B", ("2B", "IF"), is_starting_today=True, starting_status_reason="starting", yahoo_o_rank=180),
                ],
            ),
            expected_moves=(),
            expected_warnings=(),
        ),
        Scenario(
            name="locked_no_game_active_warning",
            description="A locked no-game active player should stay put and emit a lock-specific warning.",
            roster=roster_with_updates(
                roster,
                {
                    "Wyatt Langford": {"starting_status_reason": "no_game", "is_locked": True},
                    "Gleyber Torres": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Hunter Brown": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Jacob deGrom": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Parker Messick": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Jonah Tong": {"is_starting_today": True, "starting_status_reason": "starting"},
                },
            ),
            expected_moves=("Felix Bautista:BN->RP",),
            expected_warnings=(
                "No eligible starting replacement found for William Contreras at C.",
                "Wyatt Langford is locked at CF; no change attempted.",
            ),
        ),
        Scenario(
            name="locked_bench_reliever_unavailable",
            description="A locked bench reliever should not be promoted into a generic P slot.",
            roster=roster_with_updates(
                roster,
                {
                    "Felix Bautista": {"is_locked": True},
                    "Kevin Gausman": {"is_starting_today": False, "starting_status_reason": "not_starting"},
                    "Hunter Brown": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Jacob deGrom": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Parker Messick": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Gleyber Torres": {"is_starting_today": True, "starting_status_reason": "starting"},
                },
            ),
            expected_moves=(),
            expected_warnings=(
                "No eligible starting replacement found for William Contreras at C.",
                "No eligible starting replacement found for Jonah Tong at P.",
            ),
        ),
        Scenario(
            name="locked_ss_allows_if_replacement",
            description="A locked SS should not block a replacement into the unlocked IF slot.",
            roster=roster_with_updates(
                roster,
                {
                    "Francisco Lindor": {"is_locked": True, "selected_position": "SS", "is_starting_today": True, "starting_status_reason": "starting"},
                    "Elly De La Cruz": {"selected_position": "BN", "is_starting_today": True, "starting_status_reason": "starting"},
                    "Gleyber Torres": {"selected_position": "IF", "is_starting_today": False, "starting_status_reason": "not_starting"},
                    "Jordan Westburg": {"selected_position": "2B", "is_starting_today": True, "starting_status_reason": "starting"},
                    "William Contreras": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Hunter Brown": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Jacob deGrom": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Parker Messick": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Jonah Tong": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Felix Bautista": {"starting_status_reason": "inactive_slot"},
                    "Kevin Gausman": {"is_starting_today": False, "starting_status_reason": "not_starting"},
                },
            ),
            expected_moves=("Gleyber Torres:IF->BN", "Elly De La Cruz:BN->IF"),
        ),
        Scenario(
            name="locked_sp_bad_slot_no_move",
            description="A locked SP that is not starting should remain in place while other unlocked SP slots can still improve.",
            roster=roster_with_updates(
                roster,
                {
                    "Hunter Brown": {"is_locked": True},
                    "Jacob deGrom": {"is_starting_today": False, "starting_status_reason": "not_starting"},
                    "Parker Messick": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Kevin Gausman": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Gleyber Torres": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Jonah Tong": {"is_starting_today": True, "starting_status_reason": "starting"},
                },
            ),
            expected_moves=("Jacob deGrom:SP->BN", "Kevin Gausman:BN->SP", "Felix Bautista:BN->RP"),
            expected_warnings=(
                "No eligible starting replacement found for William Contreras at C.",
                "Hunter Brown is locked at SP; no change attempted.",
            ),
        ),
        Scenario(
            name="locked_bench_star_blocks_orank_upgrade",
            description="A locked bench star should not trigger an O-Rank upgrade.",
            roster=roster_with_updates(
                roster,
                {
                    "William Contreras": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Gleyber Torres": {"selected_position": "IF", "is_starting_today": True, "starting_status_reason": "starting", "yahoo_o_rank": 80},
                    "Francisco Lindor": {"selected_position": "SS", "is_starting_today": True, "starting_status_reason": "starting", "yahoo_o_rank": 20},
                    "Elly De La Cruz": {"selected_position": "BN", "is_starting_today": True, "starting_status_reason": "starting", "yahoo_o_rank": 5, "is_locked": True},
                    "Jordan Westburg": {"selected_position": "2B", "is_starting_today": True, "starting_status_reason": "starting"},
                    "Hunter Brown": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Jacob deGrom": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Parker Messick": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Jonah Tong": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Felix Bautista": {"starting_status_reason": "inactive_slot"},
                    "Kevin Gausman": {"is_starting_today": False, "starting_status_reason": "not_starting"},
                },
            ),
            expected_moves=(),
        ),
        Scenario(
            name="projection_tiebreak_for_sp",
            description="When two starting SPs can fill the same slot, the higher projection should win.",
            roster=roster_with_updates(
                roster,
                {
                    "Hunter Brown": {"is_starting_today": False, "starting_status_reason": "not_starting"},
                    "Jacob deGrom": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Parker Messick": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Kevin Gausman": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Freddy Peralta": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Gleyber Torres": {"is_starting_today": True, "starting_status_reason": "starting"},
                    "Jonah Tong": {"is_starting_today": True, "starting_status_reason": "starting"},
                },
            ),
            expected_moves=("Hunter Brown:SP->BN", "Freddy Peralta:BN->SP", "Felix Bautista:BN->RP"),
            expected_warnings=("No eligible starting replacement found for William Contreras at C.",),
        ),
    ]
    return cases


SCENARIO_PROJECTIONS = {
    "Jo Adell": 9.0,
    "Jordan Westburg": 8.5,
    "Kevin Gausman": 8.0,
    "Felix Bautista": 7.0,
    "Freddy Peralta": 8.8,
}
