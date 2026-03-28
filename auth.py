import json
import os
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from dotenv import load_dotenv

load_dotenv()

AUTH_BASE_URL = "https://api.login.yahoo.com/oauth2/request_auth"
TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"


def build_authorization_url(
    client_id: str,
    redirect_uri: str,
    scope: str | None,
    state: str = "yahoo-fantasy-agent",
) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "language": "en-us",
        "state": state,
    }
    if scope:
        params["scope"] = scope
    query = urlencode(params)
    return f"{AUTH_BASE_URL}?{query}"


def exchange_code_for_token(
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code: str,
) -> dict[str, Any]:
    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "code": code,
        },
        auth=(client_id, client_secret),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def refresh_access_token(
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    refresh_token: str,
) -> dict[str, Any]:
    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "redirect_uri": redirect_uri,
            "refresh_token": refresh_token,
        },
        auth=(client_id, client_secret),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def load_token_file(path: str | os.PathLike[str]) -> dict[str, Any] | None:
    token_path = Path(path)
    if not token_path.exists():
        return None
    return json.loads(token_path.read_text())


def save_token_file(path: str | os.PathLike[str], token: dict[str, Any]) -> None:
    token_path = Path(path)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(json.dumps(token, indent=2, sort_keys=True))


def extract_code_from_redirect(redirect_response: str) -> str:
    parsed = urlparse(redirect_response)
    query_params = parse_qs(parsed.query)
    code = query_params.get("code", [])
    if not code:
        raise ValueError("Redirect URL did not include a code query parameter.")
    return code[0]


def interactive_token_capture(
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    scope: str,
    token_path: str,
    open_browser: bool = True,
) -> dict[str, Any]:
    authorization_url = build_authorization_url(
        client_id=client_id,
        redirect_uri=redirect_uri,
        scope=scope,
    )

    print("Open this URL in your browser and authorize the app:")
    print(authorization_url)
    if open_browser:
        webbrowser.open(authorization_url)

    redirect_response = input("Paste the full redirect URL here:\n").strip()
    code = extract_code_from_redirect(redirect_response)
    token = exchange_code_for_token(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        code=code,
    )
    save_token_file(token_path, token)
    return token


def get_tokens() -> dict[str, Any]:
    client_id = os.getenv("YAHOO_CLIENT_ID")
    client_secret = os.getenv("YAHOO_CLIENT_SECRET")
    redirect_uri = os.getenv("YAHOO_REDIRECT_URI", "oob")
    scope = os.getenv("YAHOO_SCOPE", "").strip() or None
    token_path = os.getenv("YAHOO_TOKEN_FILE", ".secrets/yahoo_token.json")
    open_browser = os.getenv("YAHOO_OPEN_AUTH_BROWSER", "true").lower() == "true"

    missing = [
        name
        for name, value in (
            ("YAHOO_CLIENT_ID", client_id),
            ("YAHOO_CLIENT_SECRET", client_secret),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    token = interactive_token_capture(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=scope,
        token_path=token_path,
        open_browser=open_browser,
    )

    print("Stored token data in", token_path)
    print("Refresh token:", token.get("refresh_token"))
    return token


if __name__ == "__main__":
    get_tokens()
