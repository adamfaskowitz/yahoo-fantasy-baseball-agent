from unittest import TestCase

from requests import HTTPError, Response

from automation import try_apply_lineup
from reporting import build_report_subject


class FakeYahooClient:
    def __init__(self, status_code: int | None = None):
        self.status_code = status_code

    def set_lineup(self, *, lineup_date: str, moves: list) -> None:
        if self.status_code is None:
            return
        response = Response()
        response.status_code = self.status_code
        raise HTTPError(response=response)


class TryApplyLineupTests(TestCase):
    def test_returns_action_required_for_forbidden_write(self) -> None:
        applied, warning = try_apply_lineup(FakeYahooClient(403), "2026-09-15", [])

        self.assertFalse(applied)
        self.assertIn("make the changes manually", warning or "")

    def test_reports_successful_write(self) -> None:
        applied, warning = try_apply_lineup(FakeYahooClient(), "2026-09-15", [])

        self.assertTrue(applied)
        self.assertIsNone(warning)

    def test_reraises_non_permission_http_errors(self) -> None:
        with self.assertRaises(HTTPError):
            try_apply_lineup(FakeYahooClient(500), "2026-09-15", [])

    def test_action_required_report_mode_replaces_dry_run_label(self) -> None:
        subject = build_report_subject(
            team_name="deGrom Reapers",
            lineup_date="2026-09-15",
            trigger_label="2026-09-15 04:00 PM PDT",
            applied=False,
            moves_count=2,
            mode_label="ACTION REQUIRED",
        )

        self.assertIn("ACTION REQUIRED", subject)
        self.assertNotIn("DRY RUN", subject)
