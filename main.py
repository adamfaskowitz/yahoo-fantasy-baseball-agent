import argparse
from datetime import date

from config import load_config
from lineup import optimize_lineup, render_plan, render_roster
from mlb_lineups import clear_caches, enrich_roster_with_starting_status
from yahoo_api import YahooFantasyClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Yahoo Fantasy Baseball lineup agent (dry-run by default)."
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Roster date in YYYY-MM-DD format. Defaults to today or YAHOO_LINEUP_DATE.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply roster changes through the Yahoo API.",
    )
    parser.add_argument(
        "--show-raw",
        action="store_true",
        help="Print the raw roster object after the summary output.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print MLB enrichment debug logs.",
    )
    return parser


def run() -> None:
    args = build_parser().parse_args()
    config = load_config(lineup_date=args.date, apply_changes=args.apply)
    client = YahooFantasyClient(config)

    raw_roster = client.get_team_roster(config.lineup_date)
    clear_caches()
    roster = enrich_roster_with_starting_status(
        raw_roster,
        date_str=config.lineup_date,
        verbose=args.verbose,
        ignore_locks=False,
    )
    plan = optimize_lineup(roster)

    print(render_roster(roster))
    print()
    print(render_plan(plan))

    if args.show_raw:
        print()
        print(roster)

    if config.apply_changes and plan.has_changes:
        client.set_lineup(
            lineup_date=roster.lineup_date or config.lineup_date or date.today().isoformat(),
            moves=plan.moves,
        )
        print()
        print("Applied lineup changes to Yahoo.")
    elif config.apply_changes:
        print()
        print("No lineup changes to apply.")


if __name__ == "__main__":
    run()
