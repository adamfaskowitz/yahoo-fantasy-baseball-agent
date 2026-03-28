from __future__ import annotations

import argparse
import csv
from pathlib import Path

from mlb_lineups import PROJECT_ROOT, SFBB_ID_MAP_PATH

DEFAULT_INPUT = Path("/Users/fasky/Downloads/SFBB Player ID Map - PLAYERIDMAP (1).csv")


def normalize_rows(source_path: Path) -> list[dict[str, str]]:
    rows_by_yahoo_id: dict[str, dict[str, str]] = {}
    with source_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            yahoo_id = (row.get("YAHOOID") or "").strip()
            mlb_id = (row.get("MLBID") or "").strip()
            if not yahoo_id or not mlb_id:
                continue

            normalized = {
                "yahoo_player_id": yahoo_id,
                "yahoo_name": (row.get("YAHOONAME") or row.get("PLAYERNAME") or "").strip(),
                "team_abbr": (row.get("TEAM") or "").strip(),
                "mlb_person_id": mlb_id,
                "mlb_name": (row.get("MLBNAME") or row.get("PLAYERNAME") or "").strip(),
                "mlb_pos": (row.get("POS") or "").strip(),
                "notes": "sfbb_playeridmap",
            }

            existing = rows_by_yahoo_id.get(yahoo_id)
            if existing is None or existing["team_abbr"] in {"", "N/A"}:
                rows_by_yahoo_id[yahoo_id] = normalized

    return sorted(rows_by_yahoo_id.values(), key=lambda row: (int(row["yahoo_player_id"]), row["mlb_name"]))


def write_rows(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "yahoo_player_id",
                "yahoo_name",
                "team_abbr",
                "mlb_person_id",
                "mlb_name",
                "mlb_pos",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize the SFBB Player ID Map into this project's Yahoo->MLB CSV format.")
    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT),
        help="Path to the downloaded SFBB Player ID Map CSV.",
    )
    parser.add_argument(
        "--output",
        default=str(SFBB_ID_MAP_PATH),
        help="Output CSV path in the project's normalized format.",
    )
    args = parser.parse_args()

    source_path = Path(args.input)
    if not source_path.exists():
        raise FileNotFoundError(f"Input CSV not found: {source_path}")

    rows = normalize_rows(source_path)
    write_rows(rows, Path(args.output))

    print(f"Imported rows: {len(rows)}")
    print(f"Output CSV: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
