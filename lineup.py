from __future__ import annotations

import math
from dataclasses import replace

from league_profiles import get_league_profile
from models import LineupPlan, PlannedMove, Player, RosterSnapshot

BENCH_POSITIONS = {"BN", "IL", "IL+", "NA", "IR"}
OUTFIELD_POSITIONS = {"LF", "CF", "RF", "OF"}
INFIELD_POSITIONS = {"1B", "2B", "3B", "SS", "IF"}
PITCHER_POSITIONS = {"SP", "RP", "P"}
FLEXIBLE_POSITIONS = {"IF", "OF", "UTIL", "P"}
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
DEFAULT_SLOT_LIMITS = {
    "C": 1,
    "1B": 1,
    "2B": 1,
    "3B": 1,
    "SS": 1,
    "IF": 1,
    "LF": 1,
    "CF": 1,
    "RF": 1,
    "OF": 1,
    "Util": 1,
    "SP": 3,
    "RP": 3,
    "P": 3,
    "BN": 5,
    "IL": 3,
    "NA": 2,
}
ACTIVE_SLOT_ORDER = ("C", "1B", "2B", "3B", "SS", "IF", "LF", "CF", "RF", "OF", "Util", "SP", "RP", "P")
YAHOO_RENDER_GROUPS = (
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
)


def is_bench_position(position: str | None) -> bool:
    return (position or "").upper() in BENCH_POSITIONS


def describe_starting_status(player: Player) -> str:
    if player.is_starting_today is True:
        return "starting"
    if player.is_starting_today is False:
        return "not starting"
    return STATUS_LABELS.get(player.starting_status_reason or "", "unknown")


def player_priority(player: Player, projections: dict[str, float]) -> float:
    projection = projections.get(player.player_key, projections.get(player.name, 0.0))
    # Hitter start state is already modeled in the global hitter status bucket,
    # so avoid double-counting it here. Keep the starter bonus for pitchers.
    starting_bonus = 120 if player.is_starting_today and (player.position_type or "").upper() == "P" else 0
    reliever_bonus = 30 if player.starting_status_reason == "reliever" else 0
    locked_penalty = -500 if player.is_locked else 0
    return projection + starting_bonus + reliever_bonus + locked_penalty


def lineup_value(player: Player, projections: dict[str, float], target_position: str | None) -> int:
    status_value_map = {
        "starting": 1_000,
        "reliever": 800,
        "player_unmapped": 350,
        "lineup_pending": 300,
        "probable_pitcher_missing": 250,
        "team_unmapped": 200,
        "not_starting": 0,
        "no_game": -100,
        "inactive_slot": -5_000,
    }
    status_key = (
        "starting"
        if player.is_starting_today is True
        else "not_starting"
        if player.is_starting_today is False
        else player.starting_status_reason or "player_unmapped"
    )
    base = status_value_map.get(status_key, 2_000)
    stickiness_bonus = 8 if player.selected_position == target_position else 0
    active_bonus = 4 if not is_bench_position(player.selected_position) else 0
    return int(base + player_priority(player, projections) + stickiness_bonus + active_bonus)


def get_slot_limits(roster: RosterSnapshot) -> dict[str, int]:
    return roster.slot_limits or DEFAULT_SLOT_LIMITS.copy()


def get_active_slot_order(roster: RosterSnapshot) -> tuple[str, ...]:
    profile = get_league_profile(roster.league_profile_key)
    return profile.active_slot_order


def get_render_groups(roster: RosterSnapshot) -> tuple[str, ...]:
    profile = get_league_profile(roster.league_profile_key)
    return profile.render_groups


def count_filled_slots(roster: RosterSnapshot) -> dict[str, int]:
    counts: dict[str, int] = {}
    for player in roster.players:
        slot = player.selected_position
        if not slot:
            continue
        counts[slot] = counts.get(slot, 0) + 1
    return counts


def open_active_slots(roster: RosterSnapshot) -> list[str]:
    limits = get_slot_limits(roster)
    filled = count_filled_slots(roster)
    slots: list[str] = []
    for slot in get_active_slot_order(roster):
        for _ in range(max(0, limits.get(slot, 0) - filled.get(slot, 0))):
            slots.append(slot)
    return slots


def can_fill_position(player: Player, target_position: str | None) -> bool:
    if not target_position:
        return False

    eligible_positions = set(player.eligible_positions)
    normalized_target = target_position.upper()

    if normalized_target in eligible_positions:
        return True
    if normalized_target == "OF" and eligible_positions & OUTFIELD_POSITIONS:
        return True
    if normalized_target == "IF" and eligible_positions & INFIELD_POSITIONS:
        return True
    if normalized_target == "CI" and eligible_positions & {"1B", "3B", "IF"}:
        return True
    if normalized_target == "MI" and eligible_positions & {"2B", "SS", "IF"}:
        return True
    if normalized_target == "UTIL":
        return (player.position_type or "").upper() == "B" or "UTIL" in eligible_positions
    if normalized_target == "P":
        return (player.position_type or "").upper() == "P" or bool(eligible_positions & PITCHER_POSITIONS)
    return False


def player_can_be_started(player: Player) -> bool:
    return player.is_starting_today is True or player.starting_status_reason == "reliever"


def player_is_pending_upgrade_candidate(player: Player) -> bool:
    return player.starting_status_reason == "lineup_pending" and player.yahoo_percent_started is not None


def player_can_replace(active_player: Player | None, replacement_player: Player) -> bool:
    if player_can_be_started(replacement_player):
        return True
    return (
        active_player is not None
        and (active_player.starting_status_reason == "no_game" or active_player.is_starting_today is False)
        and (active_player.position_type or "").upper() == "B"
        and (replacement_player.position_type or "").upper() == "B"
        and replacement_player.starting_status_reason == "lineup_pending"
    )


def player_should_be_replaced(player: Player) -> bool:
    if player.is_locked:
        return False
    if player.is_starting_today is False:
        return True
    return player.starting_status_reason == "no_game"


def replacement_reason(player: Player, replacement: Player) -> str:
    if player.starting_status_reason == "no_game":
        return f"No game today; swapped out for {replacement.name}."
    return f"Not starting today; swapped out for {replacement.name}."


def insertion_reason(player: Player, target_position: str | None) -> str:
    if player.is_starting_today is True:
        return f"Starting today and eligible at {target_position}."
    if player.starting_status_reason == "reliever":
        return f"Reliever available today and eligible at {target_position}."
    if player.starting_status_reason == "lineup_pending":
        return f"Lineup pending, but preferred over a no-game player at {target_position}."
    return f"Eligible at {target_position}."


def upgrade_reason(player: Player, replacement: Player) -> str:
    return f"Upgraded slot with higher-priority starter {replacement.name}."


def upgrade_insertion_reason(player: Player, displaced_player: Player, target_position: str | None) -> str:
    if player.is_starting_today is True:
        if (
            player.yahoo_percent_started is not None
            and displaced_player.yahoo_percent_started is not None
            and player.yahoo_average_pick is not None
            and displaced_player.yahoo_average_pick is not None
            and player.yahoo_actual_rank_last_week is not None
            and displaced_player.yahoo_actual_rank_last_week is not None
            and starting_tiebreak_score(player) > starting_tiebreak_score(displaced_player)
        ):
            return (
                f"Starting today and better Yahoo tie-break profile "
                f"(% Start {player.yahoo_percent_started} vs {displaced_player.yahoo_percent_started}, "
                f"Avg Pick {player.yahoo_average_pick:.1f} vs {displaced_player.yahoo_average_pick:.1f}, "
                f"AR last week {player.yahoo_actual_rank_last_week} vs {displaced_player.yahoo_actual_rank_last_week}) "
                f"at {target_position}."
            )
        return f"Starting today and ranks above {displaced_player.name} at {target_position}."
    if player.starting_status_reason == "reliever":
        return f"Reliever available today and ranks above {displaced_player.name} at {target_position}."
    if player.starting_status_reason == "lineup_pending" and player.yahoo_percent_started is not None:
        return (
            f"Lineup pending, but Yahoo % Start ({player.yahoo_percent_started}%) "
            f"beats {displaced_player.name} at {target_position}."
        )
    return f"Higher-priority lineup option than {displaced_player.name} at {target_position}."


def pending_upgrade_value(player: Player, projections: dict[str, float], target_position: str | None) -> int:
    if not player_is_pending_upgrade_candidate(player):
        return -1_000_000
    percent_started_score = player.yahoo_percent_started or 0
    average_pick_score = normalized_average_pick_score(player)
    actual_rank_score = normalized_actual_rank_last_week_score(player)
    return int(
        percent_started_score
        + average_pick_score
        + actual_rank_score
        + player_priority(player, projections)
        + (8 if player.selected_position == target_position else 0)
    )


def normalized_average_pick_score(player: Player) -> int:
    if player.yahoo_average_pick is None:
        return 50
    bounded_pick = min(max(player.yahoo_average_pick, 1.0), 500.0)
    return int(round(100 - ((bounded_pick - 1.0) / 499.0) * 100))


def normalized_actual_rank_last_week_score(player: Player) -> int:
    if player.yahoo_actual_rank_last_week is None:
        return 0
    bounded_rank = max(player.yahoo_actual_rank_last_week, 1)
    return max(0, 100 - (bounded_rank - 1) * 5)


def starting_tiebreak_score(player: Player) -> int:
    percent_started = player.yahoo_percent_started or 0
    average_pick = normalized_average_pick_score(player)
    actual_rank = normalized_actual_rank_last_week_score(player)
    return percent_started + average_pick + actual_rank


def elite_pending_hitter_bonus(player: Player) -> int:
    if (player.position_type or "").upper() != "B":
        return 0
    if player.starting_status_reason != "lineup_pending":
        return 0
    if player.yahoo_average_pick is None or (player.yahoo_percent_started or 0) < 85:
        return 0
    if player.yahoo_average_pick <= 5:
        return 450
    if player.yahoo_average_pick <= 15:
        return 250
    if player.yahoo_average_pick <= 30:
        return 125
    return 0


def superstar_hitter_preservation_bonus(player: Player) -> int:
    if (player.position_type or "").upper() != "B":
        return 0
    if player.is_starting_today is False:
        return 0
    if player.yahoo_actual_rank_last_week != 1 and (
        player.yahoo_average_pick is None or player.yahoo_average_pick >= 5
    ):
        return 0
    return 1_000


def pending_confidence_bonus(player: Player) -> int:
    if (player.position_type or "").upper() != "B":
        return 0
    if player.starting_status_reason != "lineup_pending":
        return 0

    percent_started = player.yahoo_percent_started or 0
    actual_rank_score = normalized_actual_rank_last_week_score(player)
    average_pick_score = normalized_average_pick_score(player)

    bonus = 0
    if percent_started >= 85:
        bonus += (percent_started - 85) * 8
    if actual_rank_score >= 50:
        bonus += (actual_rank_score - 50) * 4
    if average_pick_score >= 70:
        bonus += (average_pick_score - 70) * 2
    return bonus


def pending_tiebreak_guard_bonus(player: Player) -> int:
    if (player.position_type or "").upper() != "B":
        return 0
    if player.starting_status_reason != "lineup_pending":
        return 0

    tiebreak = starting_tiebreak_score(player)
    if tiebreak >= 220:
        return 350
    if tiebreak >= 180:
        return 250
    if tiebreak >= 140:
        return 150
    if tiebreak >= 90:
        return 260
    return 0


def unresolved_warning(player: Player) -> str | None:
    if is_bench_position(player.selected_position):
        return None
    if player.is_locked and (player.is_starting_today is False or player.starting_status_reason == "no_game"):
        return f"{player.name} is locked at {player.selected_position}; no change attempted."
    if player_should_be_replaced(player):
        return f"No eligible starting replacement found for {player.name} at {player.selected_position}."
    return None


def optimize_lineup(
    roster: RosterSnapshot,
    projections: dict[str, float] | None = None,
    matchup_adjustments: dict[str, int] | None = None,
    frozen_slots: set[str] | None = None,
) -> LineupPlan:
    projections = projections or {}
    matchup_adjustments = matchup_adjustments or {}
    frozen_slots = frozen_slots or set()
    warnings: list[str] = []
    moves: list[PlannedMove] = []

    if not roster.players:
        warnings.append("Roster is empty.")
        return LineupPlan(moves=moves, warnings=warnings)

    actionable_statuses = {"starting", "not_starting", "no_game", "reliever"}
    if all(
        not (
            player.is_starting_today is not None
            or (player.starting_status_reason or "") in actionable_statuses
            or player_is_pending_upgrade_candidate(player)
        )
        for player in roster.players
    ):
        warnings.append(
            "No starting-status data is available yet. The optimizer will not move players blindly."
        )
        return LineupPlan(moves=moves, warnings=warnings)

    active_players = [player for player in roster.players if not is_bench_position(player.selected_position)]
    bench_players = [player for player in roster.players if is_bench_position(player.selected_position)]

    available_bench = bench_players[:]
    for active_player in active_players:
        if (active_player.selected_position or "") in frozen_slots:
            continue
        if not player_should_be_replaced(active_player):
            continue

        target_position = active_player.selected_position
        replacement = choose_replacement(
            position=target_position,
            active_player=active_player,
            bench_players=available_bench,
            projections=projections,
        )
        if replacement is None:
            continue

        available_bench.remove(replacement)
        moves.append(
            PlannedMove(
                player_key=active_player.player_key,
                player_name=active_player.name,
                from_position=active_player.selected_position,
                to_position="BN",
                reason=replacement_reason(active_player, replacement),
            )
        )
        moves.append(
            PlannedMove(
                player_key=replacement.player_key,
                player_name=replacement.name,
                from_position=replacement.selected_position,
                to_position=target_position,
                reason=insertion_reason(replacement, target_position),
            )
        )

    roster_after_replacements = apply_plan_to_roster(roster, LineupPlan(moves=moves, warnings=[]))
    available_bench = [
        player
        for player in roster_after_replacements.players
        if is_bench_position(player.selected_position)
    ]
    for open_slot in open_active_slots(roster_after_replacements):
        if open_slot in frozen_slots:
            continue
        replacement = choose_replacement(
            position=open_slot,
            active_player=None,
            bench_players=available_bench,
            projections=projections,
        )
        if replacement is None:
            continue
        available_bench.remove(replacement)
        moves.append(
            PlannedMove(
                player_key=replacement.player_key,
                player_name=replacement.name,
                from_position=replacement.selected_position,
                to_position=open_slot,
                reason=insertion_reason(replacement, open_slot),
            )
        )

    roster_after_open_slots = apply_plan_to_roster(roster, LineupPlan(moves=moves, warnings=[]))
    moves.extend(
        compute_global_hitter_upgrade_moves(
            roster_after_open_slots,
            projections,
            matchup_adjustments,
            frozen_slots,
        )
    )

    final_roster = apply_plan_to_roster(roster, LineupPlan(moves=moves, warnings=[]))
    for player in final_roster.players:
        if (player.selected_position or "") in frozen_slots:
            continue
        warning = unresolved_warning(player)
        if warning:
            warnings.append(warning)
    return LineupPlan(moves=moves, warnings=warnings)


def choose_replacement(
    position: str | None,
    active_player: Player | None,
    bench_players: list[Player],
    projections: dict[str, float],
) -> Player | None:
    eligible = [
        player
        for player in bench_players
        if not player.is_locked
        and player_can_replace(active_player, player)
        and can_fill_position(player, position)
    ]
    if not eligible:
        return None
    return sorted(eligible, key=lambda player: player_priority(player, projections), reverse=True)[0]


def choose_upgrade_replacement(
    active_player: Player,
    position: str | None,
    bench_players: list[Player],
    projections: dict[str, float],
) -> Player | None:
    eligible = [
        player
        for player in bench_players
        if not player.is_locked
        and player_can_be_started(player)
        and can_fill_position(player, position)
        and rank_upgrade_value(player, projections, position or "") > rank_upgrade_value(active_player, projections, position or "")
    ]
    if not eligible:
        return None
    return sorted(
        eligible,
        key=lambda player: rank_upgrade_value(player, projections, position or ""),
        reverse=True,
    )[0]


def hitter_can_be_globally_ranked(player: Player) -> bool:
    if (player.position_type or "").upper() != "B":
        return False
    return player.is_starting_today is True or (
        player.starting_status_reason == "lineup_pending"
        and player.yahoo_percent_started is not None
    )


def global_hitter_slot_value(
    player: Player,
    projections: dict[str, float],
    slot_name: str,
    matchup_adjustments: dict[str, int] | None = None,
) -> int:
    matchup_adjustments = matchup_adjustments or {}
    if not hitter_can_be_globally_ranked(player):
        return -1_000_000
    if player.is_starting_today is True:
        status_score = 1_000
        tiebreak_score = starting_tiebreak_score(player)
    else:
        status_score = 700
        tiebreak_score = (
            (player.yahoo_percent_started or 0)
            + normalized_average_pick_score(player)
            + normalized_actual_rank_last_week_score(player)
        )
    stay_bonus = 8 if player.selected_position == slot_name else 0
    flexibility_bonus = slot_flexibility_bonus(player, slot_name)
    matchup_adjustment = matchup_adjustments.get(player.player_key, 0)
    pending_superstar_bonus = elite_pending_hitter_bonus(player)
    preservation_bonus = superstar_hitter_preservation_bonus(player)
    pending_profile_bonus = pending_confidence_bonus(player)
    pending_guard_bonus = pending_tiebreak_guard_bonus(player)
    return int(
        status_score
        + tiebreak_score
        + player_priority(player, projections)
        + stay_bonus
        + flexibility_bonus
        + preservation_bonus
        + pending_superstar_bonus
        + pending_profile_bonus
        + pending_guard_bonus
        + matchup_adjustment
    )


def slot_flexibility_bonus(player: Player, slot_name: str) -> int:
    eligible_positions = {position.upper() for position in player.eligible_positions}
    normalized_slot = (slot_name or "").upper()
    bonus = 0

    if normalized_slot not in FLEXIBLE_POSITIONS and normalized_slot in eligible_positions:
        bonus += 8

    if normalized_slot == "OF" and eligible_positions & {"LF", "CF", "RF"}:
        bonus -= 4
    if normalized_slot == "IF" and eligible_positions & {"1B", "2B", "3B", "SS"}:
        bonus -= 4
    if normalized_slot == "UTIL" and ((player.position_type or "").upper() == "B") and eligible_positions - {"UTIL"}:
        bonus -= 6
    if normalized_slot == "P" and eligible_positions & {"SP", "RP"}:
        bonus -= 4

    return bonus


def compute_global_hitter_upgrade_moves(
    roster: RosterSnapshot,
    projections: dict[str, float],
    matchup_adjustments: dict[str, int] | None = None,
    frozen_slots: set[str] | None = None,
) -> list[PlannedMove]:
    matchup_adjustments = matchup_adjustments or {}
    frozen_slots = frozen_slots or set()
    active_slots = [
        (player.selected_position or "", index)
        for index, player in enumerate(roster.players)
        if not is_bench_position(player.selected_position)
        and (player.selected_position or "") not in frozen_slots
        and not player.is_locked
        and (player.position_type or "").upper() == "B"
        and hitter_can_be_globally_ranked(player)
    ]
    if not active_slots:
        return []

    candidate_players = [
        player
        for player in roster.players
        if not player.is_locked
        and (
            (
                not is_bench_position(player.selected_position)
                and (player.selected_position or "") not in frozen_slots
                and (player.position_type or "").upper() == "B"
                and hitter_can_be_globally_ranked(player)
            )
            or (
                is_bench_position(player.selected_position)
                and hitter_can_be_globally_ranked(player)
            )
        )
    ]
    if not candidate_players:
        return []

    total_nodes = 2 + len(candidate_players) + len(active_slots)
    source = 0
    sink = total_nodes - 1
    graph: list[list[dict]] = [[] for _ in range(total_nodes)]

    def add_edge(u: int, v: int, capacity: int, cost: int) -> None:
        forward = {"to": v, "rev": len(graph[v]), "cap": capacity, "cost": cost}
        backward = {"to": u, "rev": len(graph[u]), "cap": 0, "cost": -cost}
        graph[u].append(forward)
        graph[v].append(backward)

    for index, player in enumerate(candidate_players):
        player_node = 1 + index
        add_edge(source, player_node, 1, 0)
        for slot_index, (slot_name, _) in enumerate(active_slots):
            if can_fill_position(player, slot_name):
                score = global_hitter_slot_value(player, projections, slot_name, matchup_adjustments)
                add_edge(player_node, 1 + len(candidate_players) + slot_index, 1, -score)
        add_edge(player_node, sink, 1, 0)

    for slot_index in range(len(active_slots)):
        add_edge(1 + len(candidate_players) + slot_index, sink, 1, 0)

    while True:
        distance = [math.inf] * total_nodes
        parent: list[tuple[int, int] | None] = [None] * total_nodes
        distance[source] = 0
        updated = True
        for _ in range(total_nodes - 1):
            if not updated:
                break
            updated = False
            for node in range(total_nodes):
                if distance[node] == math.inf:
                    continue
                for edge_index, edge in enumerate(graph[node]):
                    if edge["cap"] <= 0:
                        continue
                    next_distance = distance[node] + edge["cost"]
                    if next_distance < distance[edge["to"]]:
                        distance[edge["to"]] = next_distance
                        parent[edge["to"]] = (node, edge_index)
                        updated = True

        if parent[sink] is None or distance[sink] >= 0:
            break

        node = sink
        while node != source:
            prev_node, edge_index = parent[node]
            edge = graph[prev_node][edge_index]
            edge["cap"] -= 1
            graph[node][edge["rev"]]["cap"] += 1
            node = prev_node

    slot_assignments: dict[tuple[str, int], Player] = {}
    slot_node_start = 1 + len(candidate_players)
    for index, player in enumerate(candidate_players):
        player_node = 1 + index
        for edge in graph[player_node]:
            if slot_node_start <= edge["to"] < slot_node_start + len(active_slots) and edge["cap"] == 0:
                slot_assignments[active_slots[edge["to"] - slot_node_start]] = player
                break

    if not slot_assignments:
        return []

    players_by_key = {player.player_key: player for player in roster.players}
    assigned_positions: dict[str, str] = {}
    for slot, assigned_player in slot_assignments.items():
        assigned_positions[assigned_player.player_key] = slot[0]

    moves: list[PlannedMove] = []
    assigned_keys = set(assigned_positions)
    active_hitter_keys = {
        player.player_key
        for player in roster.players
        if not is_bench_position(player.selected_position)
        and (player.selected_position or "") not in frozen_slots
        and not player.is_locked
        and (player.position_type or "").upper() == "B"
        and hitter_can_be_globally_ranked(player)
    }

    for player_key in active_hitter_keys:
        player = players_by_key[player_key]
        new_position = assigned_positions.get(player_key, "BN")
        if new_position != player.selected_position:
            if new_position == "BN":
                replacement = next(
                    (
                        assigned_player
                        for assigned_player in slot_assignments.values()
                        if assigned_player.player_key != player_key
                        and assigned_player.selected_position != assigned_positions.get(assigned_player.player_key)
                        and assigned_positions.get(assigned_player.player_key) == player.selected_position
                    ),
                    None,
                )
                reason = upgrade_reason(player, replacement) if replacement is not None else "Benched after global lineup optimization."
            else:
                reason = move_reason(player, player.selected_position, new_position)
            moves.append(
                PlannedMove(
                    player_key=player.player_key,
                    player_name=player.name,
                    from_position=player.selected_position,
                    to_position=new_position,
                    reason=reason,
                )
            )

    for player_key in assigned_keys - active_hitter_keys:
        player = players_by_key[player_key]
        new_position = assigned_positions[player_key]
        if new_position != player.selected_position:
            displaced_player = next(
                (
                    active_player
                    for active_player in roster.players
                    if active_player.selected_position == new_position
                    and active_player.player_key != player_key
                ),
                None,
            )
            moves.append(
                PlannedMove(
                    player_key=player.player_key,
                    player_name=player.name,
                    from_position=player.selected_position,
                    to_position=new_position,
                    reason=upgrade_insertion_reason(player, displaced_player or player, new_position),
                )
            )

    return sorted(moves, key=lambda move: 0 if move.to_position == "BN" else 1)


def move_reason(player: Player, current_position: str | None, target_position: str | None) -> str:
    if is_bench_position(current_position) and not is_bench_position(target_position):
        return f"Assigned to {target_position} in optimized lineup."
    if not is_bench_position(current_position) and is_bench_position(target_position):
        if player.starting_status_reason == "no_game":
            return "Benched because there is no game."
        if player.is_starting_today is False:
            return "Benched because player is not starting."
        return "Benched after global lineup optimization."
    return f"Reassigned from {current_position} to {target_position} in optimized lineup."


def compute_rank_upgrade_moves(
    roster: RosterSnapshot,
    projections: dict[str, float],
) -> list[PlannedMove]:
    active_upgrade_pool = [
        player
        for player in roster.players
        if not is_bench_position(player.selected_position)
        and not player.is_locked
        and player_can_be_started(player)
    ]
    bench_ranked_pool = [
        player
        for player in roster.players
        if is_bench_position(player.selected_position)
        and not player.is_locked
        and player_can_be_started(player)
        and player.yahoo_average_pick is not None
    ]
    if not bench_ranked_pool:
        return []

    player_nodes = active_upgrade_pool + bench_ranked_pool
    slot_nodes = [(player.selected_position or "", index) for index, player in enumerate(active_upgrade_pool)]
    total_nodes = 2 + len(player_nodes) + len(slot_nodes)
    source = 0
    sink = total_nodes - 1

    graph: list[list[dict]] = [[] for _ in range(total_nodes)]

    def add_edge(u: int, v: int, capacity: int, cost: int) -> None:
        forward = {"to": v, "rev": len(graph[v]), "cap": capacity, "cost": cost}
        backward = {"to": u, "rev": len(graph[u]), "cap": 0, "cost": -cost}
        graph[u].append(forward)
        graph[v].append(backward)

    for index, player in enumerate(player_nodes):
        player_node = 1 + index
        add_edge(source, player_node, 1, 0)
        for slot_index, (slot_name, _) in enumerate(slot_nodes):
            if can_fill_position(player, slot_name):
                score = rank_upgrade_value(player, projections, slot_name)
                add_edge(player_node, 1 + len(player_nodes) + slot_index, 1, -score)
        add_edge(player_node, sink, 1, 0)

    for slot_index in range(len(slot_nodes)):
        add_edge(1 + len(player_nodes) + slot_index, sink, 1, 0)

    while True:
        distance = [math.inf] * total_nodes
        parent: list[tuple[int, int] | None] = [None] * total_nodes
        distance[source] = 0

        updated = True
        for _ in range(total_nodes - 1):
            if not updated:
                break
            updated = False
            for node in range(total_nodes):
                if distance[node] == math.inf:
                    continue
                for edge_index, edge in enumerate(graph[node]):
                    if edge["cap"] <= 0:
                        continue
                    next_distance = distance[node] + edge["cost"]
                    if next_distance < distance[edge["to"]]:
                        distance[edge["to"]] = next_distance
                        parent[edge["to"]] = (node, edge_index)
                        updated = True

        if parent[sink] is None:
            break

        if distance[sink] >= 0:
            break

        node = sink
        while node != source:
            prev_node, edge_index = parent[node]
            edge = graph[prev_node][edge_index]
            edge["cap"] -= 1
            graph[node][edge["rev"]]["cap"] += 1
            node = prev_node

    best_candidate: tuple[int, str, str] | None = None
    for index, player in enumerate(player_nodes):
        player_node = 1 + index
        for edge in graph[player_node]:
            slot_node_start = 1 + len(player_nodes)
            slot_node_end = slot_node_start + len(slot_nodes)
            if slot_node_start <= edge["to"] < slot_node_end and edge["cap"] == 0:
                slot_name, _ = slot_nodes[edge["to"] - slot_node_start]
                if player.selected_position != slot_name:
                    if is_bench_position(player.selected_position):
                        candidate_score = rank_upgrade_value(player, projections, slot_name)
                        if best_candidate is None or candidate_score > best_candidate[0]:
                            best_candidate = (candidate_score, player.player_key, slot_name)
                break
    if best_candidate is not None:
        _, player_key, slot_name = best_candidate
        return build_rank_upgrade_moves(roster, player_key, slot_name, slot_nodes, graph, player_nodes)
    return []


def rank_upgrade_value(player: Player, projections: dict[str, float], slot_name: str) -> int:
    if player.yahoo_average_pick is None and player.yahoo_actual_rank_last_week is None:
        return -1_000_000
    return int(
        1_000
        + starting_tiebreak_score(player)
        + player_priority(player, projections)
        + (8 if player.selected_position == slot_name else 0)
    )


def build_rank_upgrade_moves(
    roster: RosterSnapshot,
    bench_player_key: str,
    target_slot: str,
    slot_nodes: list[tuple[str, int]],
    graph: list[list[dict]],
    player_nodes: list[Player],
) -> list[PlannedMove]:
    slot_node_start = 1 + len(player_nodes)
    slot_to_player_key: dict[tuple[str, int], str] = {}
    for index, player in enumerate(player_nodes):
        player_node = 1 + index
        for edge in graph[player_node]:
            if slot_node_start <= edge["to"] < slot_node_start + len(slot_nodes) and edge["cap"] == 0:
                slot_to_player_key[slot_nodes[edge["to"] - slot_node_start]] = player.player_key

    target_slot_instance = next((slot for slot in slot_nodes if slot[0] == target_slot and slot_to_player_key.get(slot) == bench_player_key), None)
    if target_slot_instance is None:
        return []

    displaced_player_key = next(
        (
            player.player_key
            for player in roster.players
            if player.selected_position == target_slot and player.player_key != bench_player_key
        ),
        None,
    )
    if displaced_player_key is None:
        return []

    players_by_key = {player.player_key: player for player in roster.players}
    bench_player = players_by_key[bench_player_key]
    displaced_player = players_by_key[displaced_player_key]

    moves = [
        PlannedMove(
            player_key=bench_player.player_key,
            player_name=bench_player.name,
            from_position=bench_player.selected_position,
            to_position=target_slot,
            reason=upgrade_insertion_reason(bench_player, displaced_player, target_slot),
        ),
    ]

    reassigned_slot = next(
        (
            slot_name
            for (slot_name, _), player_key in slot_to_player_key.items()
            if player_key == displaced_player.player_key
        ),
        None,
    )
    if reassigned_slot and reassigned_slot != displaced_player.selected_position:
        moves.append(
            PlannedMove(
                player_key=displaced_player.player_key,
                player_name=displaced_player.name,
                from_position=displaced_player.selected_position,
                to_position=reassigned_slot,
                reason=f"Reassigned from {displaced_player.selected_position} to {reassigned_slot} in optimized lineup.",
            )
        )
    elif reassigned_slot is None:
        moves.append(
            PlannedMove(
                player_key=displaced_player.player_key,
                player_name=displaced_player.name,
                from_position=displaced_player.selected_position,
                to_position="BN",
                reason=upgrade_reason(displaced_player, bench_player),
            )
        )
    return sorted(moves, key=lambda move: 0 if move.to_position == "BN" else 1)


def apply_plan_to_roster(roster: RosterSnapshot, plan: LineupPlan) -> RosterSnapshot:
    players = {player.player_key: player for player in roster.players}
    for move in plan.moves:
        player = players.get(move.player_key)
        if player is None:
            continue
        players[move.player_key] = replace(player, selected_position=move.to_position)
    return replace(roster, players=list(players.values()))


def render_group_name(player: Player) -> str:
    slot = (player.selected_position or "").upper()
    position_type = (player.position_type or "").upper()
    if slot == "BN":
        return "BN_P" if position_type == "P" else "BN_B"
    if slot in {"IL", "IL+"}:
        return "IL_P" if position_type == "P" else "IL_B"
    if slot == "NA":
        return "NA_P" if position_type == "P" else "NA_B"
    return slot


def roster_sort_key(roster: RosterSnapshot, player: Player) -> tuple[int, int, str]:
    group = render_group_name(player)
    try:
        group_index = get_render_groups(roster).index(group)
    except ValueError:
        group_index = len(get_render_groups(roster))

    slot_index = 0
    if group in {"SP", "RP", "P"}:
        same_group_players = [
            current
            for current in roster.players
            if render_group_name(current) == group
        ]
        same_group_players.sort(key=lambda item: item.name)
        slot_index = same_group_players.index(player)
    return group_index, slot_index, player.name


def status_label(player: Player) -> str:
    status = describe_starting_status(player)
    if player.is_locked:
        status = f"{status}; locked"
    return status


def render_roster(roster: RosterSnapshot) -> str:

    slot_limits = get_slot_limits(roster)
    lines = [
        f"Team: {roster.team_name or roster.team_key}",
        f"Date: {roster.lineup_date or 'unknown'}",
        "Slots: "
        + ", ".join(
            f"{slot} x{slot_limits[slot]}"
            for slot in get_active_slot_order(roster)
            if slot in slot_limits
        ),
        "Roster:",
    ]
    for player in sorted(roster.players, key=lambda item: roster_sort_key(roster, item)):
        status = status_label(player)
        lines.append(
            f"- {player.selected_position or '?':<4} {player.name} ({player.display_position}) [{status}]"
        )
    return "\n".join(lines)


def render_plan(plan: LineupPlan) -> str:
    lines = ["Plan:"]
    if plan.warnings:
        for warning in plan.warnings:
            lines.append(f"- Warning: {warning}")
    if not plan.moves:
        lines.append("- No changes proposed.")
        return "\n".join(lines)

    for move in plan.moves:
        lines.append(
            f"- {move.player_name}: {move.from_position or '?'} -> {move.to_position or '?'} ({move.reason})"
        )
    return "\n".join(lines)
