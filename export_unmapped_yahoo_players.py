from __future__ import annotations

import argparse
import csv
import math
import xml.etree.ElementTree as ET
from pathlib import Path

from config import load_config
from mlb_lineups import lookup_local_mlb_person_id
from models import Player
from yahoo_api import YahooFantasyClient, parse_player

BASE_URL = "https://fantasysports.yahooapis.com/fantasy/v2"


def derive_league_key(team_key: str) -> str:
    if ".t." not in team_key:
        raise ValueError(f"Could not derive league key from team key: {team_key}")
    return team_key.split(".t.", 1)[0]


def local_name(tag: str) -> str:
    return tag.split("}", 1)[-1]


def parse_players(xml_text: str) -> list[Player]:
    root = ET.fromstring(xml_text)
    players: list[Player] = []
    for node in root.iter():
        if local_name(node.tag) == "player":
            players.append(parse_player(node))
    return players


def fetch_league_players(client: YahooFantasyClient, league_key: str, page_size: int = 25) -> list[Player]:
    players: dict[str, Player] = {}
    start = 0

    while True:
        response = client.session.get(
            f"{BASE_URL}/league/{league_key}/players;start={start};count={page_size}",
            timeout=30,
        )
        response.raise_for_status()
        batch = parse_players(response.text)
        if not batch:
            break

        for player in batch:
            players[player.player_id] = player

        if len(batch) < page_size:
            break
        start += page_size

    return list(players.values())


def export_unmapped_players(players: list[Player], output_path: Path) -> tuple[int, int]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mapped = 0
    unmapped_rows: list[dict[str, str]] = []

    for player in sorted(players, key=lambda item: (item.editorial_team_abbr or "", item.name)):
        mlb_person_id = lookup_local_mlb_person_id(player)
        if mlb_person_id:
            mapped += 1
            continue

        unmapped_rows.append(
            {
                "yahoo_player_id": player.player_id,
                "yahoo_name": player.name,
                "team_abbr": player.editorial_team_abbr or "",
                "display_position": player.display_position or "",
                "primary_position": player.primary_position or "",
                "eligible_positions": ",".join(player.eligible_positions),
            }
        )

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "yahoo_player_id",
                "yahoo_name",
                "team_abbr",
                "display_position",
                "primary_position",
                "eligible_positions",
            ],
        )
        writer.writeheader()
        writer.writerows(unmapped_rows)

    return mapped, len(unmapped_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Yahoo league players without MLB ID mappings.")
    parser.add_argument(
        "--output",
        default="data/yahoo_unmapped_player_pool.csv",
        help="Output CSV path for unmapped players.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=25,
        help="Yahoo pagination size for league players requests.",
    )
    args = parser.parse_args()

    config = load_config(apply_changes=False)
    client = YahooFantasyClient(config)
    league_key = derive_league_key(config.yahoo_team_key)
    players = fetch_league_players(client, league_key=league_key, page_size=args.page_size)
    mapped_count, unmapped_count = export_unmapped_players(players, Path(args.output))

    print(f"League key: {league_key}")
    print(f"Total players fetched: {len(players)}")
    print(f"Mapped players: {mapped_count}")
    print(f"Unmapped players: {unmapped_count}")
    print(f"Output CSV: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
