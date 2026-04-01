from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from automation_state import detect_manual_override_slots, load_state, save_state, update_state_for_lineup
from config import load_config
from lineup import optimize_lineup, render_plan, render_roster
from mlb_lineups import clear_caches, enrich_roster_with_starting_status, get_schedule_for_date
from reporting import (
    build_html_report,
    build_report_body,
    build_report_subject,
    load_email_config,
    send_email_report,
)
from yahoo_api import YahooFantasyClient

LOCAL_TZ = ZoneInfo("America/Los_Angeles")


def floor_to_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def floor_to_half_hour(dt: datetime) -> datetime:
    minute = 30 if dt.minute >= 30 else 0
    return dt.replace(minute=minute, second=0, microsecond=0)


def compute_trigger_windows(lineup_date: str) -> list[datetime]:
    windows: set[datetime] = set()
    for game in get_schedule_for_date(lineup_date):
        game_date = game.get("gameDate")
        if not game_date:
            continue
        start_utc = datetime.fromisoformat(game_date.replace("Z", "+00:00"))
        start_local = start_utc.astimezone(LOCAL_TZ)
        rounded_start = floor_to_hour(start_local)
        trigger_time = rounded_start - timedelta(minutes=30)
        windows.add(trigger_time)
    return sorted(windows)


def format_trigger_label(trigger_time: datetime) -> str:
    return trigger_time.strftime("%Y-%m-%d %I:%M %p %Z")


def should_run_now(lineup_date: str, now_local: datetime) -> datetime | None:
    current_bucket = floor_to_half_hour(now_local)
    for trigger_time in compute_trigger_windows(lineup_date):
        if trigger_time == current_bucket:
            return trigger_time
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scheduled Yahoo lineup automation entrypoint.")
    parser.add_argument("--date", default=None, help="Lineup date in YYYY-MM-DD format.")
    parser.add_argument(
        "--now",
        default=None,
        help="Override current local time in ISO format for testing, e.g. 2026-03-26T15:30:00-07:00.",
    )
    parser.add_argument("--force", action="store_true", help="Run even if current time is not a trigger window.")
    parser.add_argument("--apply", action="store_true", help="Apply lineup changes to Yahoo.")
    parser.add_argument("--verbose", action="store_true", help="Print MLB enrichment debug logs.")
    parser.add_argument("--email", action="store_true", help="Send an email report if SMTP is configured.")
    return parser.parse_args()


def resolve_now(now_arg: str | None) -> datetime:
    if not now_arg:
        return datetime.now(LOCAL_TZ)
    parsed = datetime.fromisoformat(now_arg)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=LOCAL_TZ)
    return parsed.astimezone(LOCAL_TZ)


def main() -> int:
    args = parse_args()
    now_local = resolve_now(args.now)
    config = load_config(lineup_date=args.date, apply_changes=args.apply)

    trigger_time = should_run_now(config.lineup_date, now_local)
    if trigger_time is None and not args.force:
        windows = ", ".join(format_trigger_label(window) for window in compute_trigger_windows(config.lineup_date))
        print(f"Skipping run at {now_local.isoformat()}: no trigger window matched.")
        print(f"Today's trigger windows: {windows or 'none'}")
        return 0

    trigger_label = format_trigger_label(trigger_time or floor_to_half_hour(now_local))
    client = YahooFantasyClient(config)
    raw_roster = client.get_team_roster(config.lineup_date)
    clear_caches()
    roster = enrich_roster_with_starting_status(
        raw_roster,
        date_str=config.lineup_date,
        verbose=args.verbose,
        ignore_locks=False,
    )
    state = load_state()
    frozen_slots = detect_manual_override_slots(state, config.lineup_date, roster)
    if frozen_slots:
        frozen_label = ", ".join(sorted(frozen_slots))
        print(f"Respecting manual overrides in slots: {frozen_label}")
    plan = optimize_lineup(roster, frozen_slots=frozen_slots)

    print(f"Triggered run for {trigger_label}")
    print(render_plan(plan))
    print()
    print(render_roster(roster))

    applied = args.apply
    if args.apply and plan.has_changes:
        client.set_lineup(lineup_date=roster.lineup_date or config.lineup_date, moves=plan.moves)
        raw_roster = client.get_team_roster(config.lineup_date)
        clear_caches()
        roster = enrich_roster_with_starting_status(
            raw_roster,
            date_str=config.lineup_date,
            verbose=False,
            ignore_locks=False,
        )

    if args.apply:
        state = update_state_for_lineup(
            state,
            config.lineup_date,
            roster,
            frozen_slots=frozen_slots,
        )
        save_state(state)

    should_send_email = args.email and (plan.has_changes or args.force)

    if should_send_email:
        email_config = load_email_config()
        if email_config is None:
            raise RuntimeError("Email requested, but SMTP_* environment variables are incomplete.")
        subject = build_report_subject(
            lineup_date=config.lineup_date,
            trigger_label=trigger_label,
            applied=applied,
            moves_count=len(plan.moves),
        )
        body = build_report_body(
            lineup_date=config.lineup_date,
            trigger_label=trigger_label,
            applied=applied,
            roster=roster,
            plan=plan,
        )
        html_body = build_html_report(
            lineup_date=config.lineup_date,
            trigger_label=trigger_label,
            applied=applied,
            roster=roster,
            plan=plan,
        )
        send_email_report(config=email_config, subject=subject, body=body, html_body=html_body)
        print("Email report sent.")
    elif args.email:
        print("No email sent because no moves were proposed and this was not a forced/manual run.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
