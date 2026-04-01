from __future__ import annotations

import json
from pathlib import Path

from models import RosterSnapshot

STATE_PATH = Path(".automation/agent_state.json")


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"lineups": {}}
    try:
        data = json.loads(STATE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {"lineups": {}}
    if not isinstance(data, dict):
        return {"lineups": {}}
    data.setdefault("lineups", {})
    return data


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def active_slot_map(roster: RosterSnapshot) -> dict[str, str]:
    return {
        player.selected_position or "": player.player_key
        for player in roster.players
        if player.selected_position and player.selected_position not in {"BN", "IL", "IL+", "NA", "IR"}
    }


def detect_manual_override_slots(state: dict, lineup_date: str, roster: RosterSnapshot) -> set[str]:
    lineup_state = state.get("lineups", {}).get(lineup_date, {})
    previous_slots: dict[str, str] = lineup_state.get("last_agent_applied_slots", {}) or {}
    frozen_slots = set(lineup_state.get("manual_frozen_slots", []) or [])
    if not previous_slots:
        return frozen_slots

    current_slots = active_slot_map(roster)
    for slot_name, previous_player_key in previous_slots.items():
        current_player_key = current_slots.get(slot_name)
        if current_player_key is None or current_player_key == previous_player_key:
            continue
        frozen_slots.add(slot_name)
    return frozen_slots


def update_state_for_lineup(
    state: dict,
    lineup_date: str,
    roster: RosterSnapshot,
    *,
    frozen_slots: set[str],
) -> dict:
    lineups = dict(state.get("lineups", {}))
    lineups[lineup_date] = {
        "last_agent_applied_slots": active_slot_map(roster),
        "manual_frozen_slots": sorted(frozen_slots),
    }
    # Keep the file small; we only need recent days for manual-override protection.
    trimmed_dates = sorted(lineups)[-7:]
    state["lineups"] = {date_key: lineups[date_key] for date_key in trimmed_dates}
    return state
