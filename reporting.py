from __future__ import annotations

import html
import os
import smtplib
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from lineup import render_group_name, render_plan, render_roster, roster_sort_key, status_label
from models import LineupPlan, PlannedMove, Player, RosterSnapshot
from mlb_lineups import TEAM_ABBR_TO_MLB_ID, get_team_game

LOCAL_TZ = ZoneInfo("America/Los_Angeles")


@dataclass(frozen=True)
class EmailConfig:
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_from: str
    smtp_to: tuple[str, ...]
    use_tls: bool
    use_ssl: bool


def load_email_config() -> EmailConfig | None:
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_username = os.getenv("SMTP_USERNAME", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_from = os.getenv("SMTP_FROM", "").strip()
    raw_recipients = os.getenv("SMTP_TO", "").strip()
    if not all((smtp_host, smtp_username, smtp_password, smtp_from, raw_recipients)):
        return None

    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    recipients = tuple(
        recipient.strip()
        for recipient in raw_recipients.split(",")
        if recipient.strip()
    )
    return EmailConfig(
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_username=smtp_username,
        smtp_password=smtp_password,
        smtp_from=smtp_from,
        smtp_to=recipients,
        use_tls=os.getenv("SMTP_USE_TLS", "true").strip().lower() in {"1", "true", "yes", "on"},
        use_ssl=os.getenv("SMTP_USE_SSL", "false").strip().lower() in {"1", "true", "yes", "on"},
    )


def build_report_subject(
    *,
    lineup_date: str,
    trigger_label: str,
    applied: bool,
    moves_count: int,
) -> str:
    mode = "APPLIED" if applied else "DRY RUN"
    return f"[Yahoo Lineup Agent] {mode} {lineup_date} {trigger_label} ({moves_count} moves)"


def build_report_body(
    *,
    lineup_date: str,
    trigger_label: str,
    applied: bool,
    roster: RosterSnapshot,
    plan: LineupPlan,
) -> str:
    mode = "APPLIED" if applied else "DRY RUN"
    return "\n\n".join(
        [
            f"Yahoo Lineup Agent Report\nDate: {lineup_date}\nTrigger: {trigger_label}\nMode: {mode}",
            render_plan(plan),
            render_roster(roster),
        ]
    )


def move_map(plan: LineupPlan) -> tuple[dict[str, PlannedMove], dict[str, PlannedMove]]:
    bench_out: dict[str, PlannedMove] = {}
    bench_in: dict[str, PlannedMove] = {}
    for move in plan.moves:
        if (move.to_position or "").upper() == "BN":
            bench_out[move.player_key] = move
        else:
            bench_in[move.player_key] = move
    return bench_out, bench_in


def player_highlight_class(player: Player, bench_out: dict[str, PlannedMove], bench_in: dict[str, PlannedMove]) -> str:
    if player.player_key in bench_out:
        return "bench-out"
    if player.player_key in bench_in:
        return "bench-in"
    return ""


def move_badge(player: Player, bench_out: dict[str, PlannedMove], bench_in: dict[str, PlannedMove]) -> str:
    move = bench_out.get(player.player_key)
    if move:
        return f'<span class="move-badge move-out">OUT -> {html.escape(move.to_position or "?")}</span>'
    move = bench_in.get(player.player_key)
    if move:
        return f'<span class="move-badge move-in">IN -> {html.escape(move.to_position or "?")}</span>'
    return ""


def is_inactive_row(player: Player) -> bool:
    return (player.selected_position or "").upper() in {"BN", "IL", "IL+", "NA"}


def format_game_line(player: Player, lineup_date: str) -> tuple[str, str]:
    if not player.editorial_team_abbr or player.editorial_team_abbr not in TEAM_ABBR_TO_MLB_ID:
        return "", ""
    game = get_team_game(lineup_date, TEAM_ABBR_TO_MLB_ID[player.editorial_team_abbr])
    if not game:
        return "", ""

    away = game["teams"]["away"]["team"]
    home = game["teams"]["home"]["team"]
    is_away = away["id"] == TEAM_ABBR_TO_MLB_ID[player.editorial_team_abbr]
    away_abbr = away.get("abbreviation") or away.get("teamCode") or away.get("name", "")
    home_abbr = home.get("abbreviation") or home.get("teamCode") or home.get("name", "")
    opp = f"@ {home_abbr}" if is_away else f"vs {away_abbr}"

    game_date = game.get("gameDate")
    if not game_date:
        return opp, ""
    start_local = datetime.fromisoformat(game_date.replace("Z", "+00:00")).astimezone(LOCAL_TZ)
    return opp, start_local.strftime("%-I:%M %p")


def format_percent(value: int | None) -> str:
    if value is None:
        return "&mdash;"
    return f"{value}%"


def build_yahoo_team_url(team_key: str | None) -> str | None:
    if not team_key:
        return None
    parts = team_key.split(".")
    if len(parts) != 5 or parts[1] != "l" or parts[3] != "t":
        return None
    _, _, league_id, _, team_id = parts
    if not (league_id.isdigit() and team_id.isdigit()):
        return None
    game_code = "b1"
    return f"https://baseball.fantasysports.yahoo.com/{game_code}/{league_id}/{team_id}"


def status_badges(player: Player) -> str:
    badges: list[str] = []
    if player.is_locked:
        badges.append('<span class="status-chip chip-locked">Locked</span>')
    if player.is_starting_today is True:
        badges.append('<span class="status-chip chip-starting">Starting</span>')
    elif player.starting_status_reason == "lineup_pending":
        badges.append('<span class="status-chip chip-pending">Pending</span>')
    elif player.starting_status_reason == "no_game":
        badges.append('<span class="status-chip chip-no-game">No Game</span>')
    elif player.starting_status_reason == "reliever":
        badges.append('<span class="status-chip chip-reliever">RP</span>')
    elif player.is_starting_today is False:
        badges.append('<span class="status-chip chip-not-starting">Out</span>')
    return "".join(badges)


def build_html_report(
    *,
    lineup_date: str,
    trigger_label: str,
    applied: bool,
    roster: RosterSnapshot,
    plan: LineupPlan,
) -> str:
    mode = "APPLIED" if applied else "DRY RUN"
    bench_out, bench_in = move_map(plan)
    rows_html: list[str] = []
    current_section: str | None = None
    for player in sorted(roster.players, key=lambda item: roster_sort_key(roster, item)):
        section = "Pitchers" if (player.position_type or "").upper() == "P" else "Batters"
        if section != current_section:
            rows_html.append(
                f'<tr class="section-row"><td colspan="8">{section}</td></tr>'
            )
            current_section = section
        slot = html.escape(player.selected_position or "?")
        name = html.escape(player.name)
        status = html.escape(status_label(player))
        badge = move_badge(player, bench_out, bench_in)
        highlight = player_highlight_class(player, bench_out, bench_in)
        opp, game_time = format_game_line(player, lineup_date)
        meta_team = html.escape(player.editorial_team_abbr or "")
        meta_primary = html.escape(player.display_position or player.primary_position or "")
        percent_started = format_percent(player.yahoo_percent_started)
        percent_owned = format_percent(player.yahoo_percent_owned)
        chips = status_badges(player)
        headshot = (
            f'<img class="headshot" src="{html.escape(player.image_url)}" alt="{name}">'
            if player.image_url
            else '<div class="headshot placeholder"></div>'
        )
        game_meta = ""
        if game_time or opp:
            game_bits = " ".join(part for part in [game_time, opp] if part)
            game_meta = f'<div class="submeta game">{html.escape(game_bits)}</div>'
        opponent = html.escape(opp) if opp else "&mdash;"
        rows_html.append(
            f'<tr class="{highlight}">'
            f'<td class="slot"><span class="slot-pill">{slot}</span></td>'
            f'<td class="player-cell">{headshot}<div class="player-copy"><div class="player-name">{name}</div><div class="submeta">{meta_team} - {meta_primary}</div><div class="chip-row">{chips}</div>{game_meta}</div></td>'
            f'<td class="opp">{opponent}</td>'
            f'<td class="percent">{percent_started}</td>'
            f'<td class="percent">{percent_owned}</td>'
            f'<td class="status">{status}</td>'
            f'<td class="move">{badge or "&mdash;"}</td>'
            "</tr>"
        )

    warnings_html = "".join(
        f"<li>{html.escape(warning)}</li>"
        for warning in plan.warnings
    ) or "<li>No warnings.</li>"
    moves_html = "".join(
        f"<li><strong>{html.escape(move.player_name)}</strong>: "
        f"{html.escape(move.from_position or '?')} -> {html.escape(move.to_position or '?')} "
        f"({html.escape(move.reason)})</li>"
        for move in plan.moves
    ) or "<li>No changes proposed.</li>"
    yahoo_team_url = build_yahoo_team_url(roster.team_key)
    open_team_button = (
        f'<a class="open-team-button" href="{html.escape(yahoo_team_url)}">Open Yahoo My Team</a>'
        if yahoo_team_url
        else ""
    )

    return f"""\
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f3f6fb;
      color: #152033;
      margin: 0;
      padding: 24px;
    }}
    .card {{
      max-width: 1120px;
      margin: 0 auto;
      background: #ffffff;
      border: 1px solid #d7deea;
      border-radius: 14px;
      overflow: hidden;
      box-shadow: 0 12px 30px rgba(20, 32, 51, 0.08);
    }}
    .header {{
      background: linear-gradient(180deg, #f8fafc, #edf2f8);
      color: #263443;
      border-bottom: 1px solid #d8e0ea;
      padding: 20px 24px;
    }}
    .header h1 {{
      margin: 0 0 6px 0;
      font-size: 22px;
    }}
    .meta {{
      font-size: 13px;
      color: #556476;
    }}
    .header-actions {{
      margin-top: 14px;
      text-align: center;
    }}
    .open-team-button {{
      display: inline-block;
      text-decoration: none;
      background: #1161d8;
      color: #ffffff;
      border-radius: 999px;
      padding: 11px 16px;
      font-size: 13px;
      font-weight: 700;
      white-space: nowrap;
    }}
    .section {{
      padding: 18px 24px;
      border-top: 1px solid #e7ecf5;
    }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
    }}
    .summary-box {{
      background: #f7f9fc;
      border: 1px solid #e4e9f3;
      border-radius: 10px;
      padding: 12px;
      font-size: 13px;
    }}
    .summary-box strong {{
      display: block;
      font-size: 18px;
      margin-bottom: 4px;
    }}
    h2 {{
      margin: 0 0 12px 0;
      font-size: 16px;
      color: #24344f;
    }}
    ul {{
      margin: 0;
      padding-left: 18px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    thead tr.super th {{
      background: #f5f7fa;
      color: #5b6673;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      border-bottom: 0;
    }}
    th {{
      text-align: left;
      padding: 14px 10px;
      background: #f0f2f5;
      color: #263443;
      border: 1px solid #d7deea;
      font-size: 16px;
    }}
    td {{
      padding: 12px 10px;
      border: 1px solid #dfe5ee;
      vertical-align: top;
      background: #ffffff;
    }}
    td.slot {{
      width: 78px;
      text-align: center;
    }}
    .slot-pill {{
      display: inline-block;
      min-width: 56px;
      padding: 12px 16px;
      border-radius: 999px;
      background: #1161d8;
      color: #ffffff;
      font-weight: 800;
      font-size: 18px;
      line-height: 1;
    }}
    .player-cell {{
      min-width: 360px;
      display: flex;
      align-items: center;
      gap: 14px;
    }}
    .headshot {{
      width: 74px;
      height: 74px;
      border-radius: 999px;
      object-fit: cover;
      border: 2px solid #dce4ee;
      background: #f8fafc;
    }}
    .headshot.placeholder {{
      display: inline-block;
      background: #eef3f8;
    }}
    .player-name {{
      font-size: 18px;
      font-weight: 700;
      color: #1363df;
      margin-bottom: 4px;
    }}
    .submeta {{
      font-size: 13px;
      color: #2e3b4a;
      font-weight: 600;
    }}
    .submeta.game {{
      margin-top: 4px;
      color: #465669;
      font-weight: 700;
    }}
    .chip-row {{
      margin-top: 6px;
    }}
    .status-chip {{
      display: inline-block;
      margin-right: 6px;
      margin-bottom: 4px;
      padding: 3px 8px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 0.02em;
    }}
    .chip-starting {{
      background: #dff5e4;
      color: #22633a;
    }}
    .chip-pending {{
      background: #fff2cc;
      color: #8a6600;
    }}
    .chip-no-game {{
      background: #eef1f5;
      color: #566579;
    }}
    .chip-reliever {{
      background: #e1efff;
      color: #1654a8;
    }}
    .chip-not-starting {{
      background: #fde2e2;
      color: #8e2e2e;
    }}
    .chip-locked {{
      background: #f3e8ff;
      color: #6b3ea8;
    }}
    td.opp, td.rank, td.percent, td.status, td.move {{
      white-space: nowrap;
      vertical-align: middle;
      font-size: 15px;
    }}
    td.percent {{
      text-align: right;
      color: #293544;
      font-weight: 700;
    }}
    td.status {{
      color: #4f6485;
    }}
    tr.bench-out {{
      background: #fdeeee;
    }}
    tr.bench-in {{
      background: #edf9ef;
    }}
    tr.bench-out td {{
      background: #fdeeee;
    }}
    tr.bench-in td {{
      background: #edf9ef;
    }}
    tr.section-row td {{
      background: linear-gradient(180deg, #f7f9fc, #eef3f8);
      color: #4c5c71;
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      padding: 12px 18px;
    }}
    .move-badge {{
      display: inline-block;
      border-radius: 999px;
      padding: 4px 8px;
      font-size: 11px;
      font-weight: 700;
    }}
    .move-out {{
      background: #f8d4d4;
      color: #922f2f;
    }}
    .move-in {{
      background: #d8f0dc;
      color: #1f6a31;
    }}
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <h1>Yahoo Lineup Agent</h1>
      <div class="meta">Date: {html.escape(lineup_date)} | Trigger: {html.escape(trigger_label)} | Mode: {html.escape(mode)}</div>
      <div class="header-actions">{open_team_button}</div>
    </div>
    <div class="section">
      <div class="summary">
        <div class="summary-box"><strong>{len(plan.moves)}</strong>Moves</div>
        <div class="summary-box"><strong>{len(plan.warnings)}</strong>Warnings</div>
        <div class="summary-box"><strong>{html.escape(roster.team_name or roster.team_key)}</strong>Team</div>
      </div>
    </div>
    <div class="section">
      <h2>Planned Changes</h2>
      <ul>{moves_html}</ul>
    </div>
    <div class="section">
      <h2>Warnings</h2>
      <ul>{warnings_html}</ul>
    </div>
    <div class="section">
      <h2>My Team</h2>
      <table>
        <thead>
          <tr class="super">
            <th colspan="3"></th>
            <th colspan="4">Fantasy</th>
          </tr>
          <tr>
            <th>Slot</th>
            <th>Batters / Pitchers</th>
            <th>Opp</th>
            <th>% Start</th>
            <th>% Ros</th>
            <th>Status</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {''.join(rows_html)}
        </tbody>
      </table>
    </div>
  </div>
</body>
</html>
"""


def send_email_report(
    *,
    config: EmailConfig,
    subject: str,
    body: str,
    html_body: str,
) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config.smtp_from
    message["To"] = ", ".join(config.smtp_to)
    message.set_content(body)
    message.add_alternative(html_body, subtype="html")

    smtp_class = smtplib.SMTP_SSL if config.use_ssl else smtplib.SMTP
    with smtp_class(config.smtp_host, config.smtp_port, timeout=30) as smtp:
        if config.use_tls and not config.use_ssl:
            smtp.starttls()
        smtp.login(config.smtp_username, config.smtp_password)
        smtp.send_message(message)
