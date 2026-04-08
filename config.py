from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from league_profiles import default_profile_key_for_team_key
from utils import parse_bool

load_dotenv()
PROJECT_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class AppConfig:
    yahoo_client_id: str
    yahoo_client_secret: str
    yahoo_redirect_uri: str
    yahoo_scope: str
    yahoo_team_key: str
    league_profile_key: str
    yahoo_token_file: str
    yahoo_access_token: str | None
    yahoo_refresh_token: str | None
    lineup_date: str
    apply_changes: bool
    open_auth_browser: bool


def load_config(
    lineup_date: str | None = None,
    apply_changes: bool | None = None,
) -> AppConfig:
    token_file = os.getenv("YAHOO_TOKEN_FILE", ".secrets/yahoo_token.json")
    token_file_path = Path(token_file).expanduser()
    if not token_file_path.is_absolute():
        token_file_path = (PROJECT_ROOT / token_file_path).resolve()

    config = AppConfig(
        yahoo_client_id=os.getenv("YAHOO_CLIENT_ID", ""),
        yahoo_client_secret=os.getenv("YAHOO_CLIENT_SECRET", ""),
        yahoo_redirect_uri=os.getenv("YAHOO_REDIRECT_URI", "oob"),
        yahoo_scope=os.getenv("YAHOO_SCOPE", ""),
        yahoo_team_key=os.getenv("YAHOO_TEAM_KEY", ""),
        league_profile_key=os.getenv("YAHOO_LEAGUE_PROFILE", "").strip()
        or default_profile_key_for_team_key(os.getenv("YAHOO_TEAM_KEY", "")),
        yahoo_token_file=str(token_file_path),
        yahoo_access_token=os.getenv("YAHOO_ACCESS_TOKEN"),
        yahoo_refresh_token=os.getenv("YAHOO_REFRESH_TOKEN"),
        lineup_date=lineup_date or os.getenv("YAHOO_LINEUP_DATE", date.today().isoformat()),
        apply_changes=apply_changes
        if apply_changes is not None
        else parse_bool(os.getenv("APPLY_CHANGES"), default=False),
        open_auth_browser=parse_bool(os.getenv("YAHOO_OPEN_AUTH_BROWSER"), default=True),
    )

    missing = [
        name
        for name, value in (
            ("YAHOO_CLIENT_ID", config.yahoo_client_id),
            ("YAHOO_CLIENT_SECRET", config.yahoo_client_secret),
            ("YAHOO_TEAM_KEY", config.yahoo_team_key),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
    return config
