# Yahoo Fantasy Baseball Lineup Agent

Python-first scaffold for a Yahoo Fantasy Baseball daily lineup agent. The current version is intentionally conservative:

- reads your roster for a target date from Yahoo
- refreshes OAuth tokens automatically
- produces a dry-run lineup plan
- only writes roster changes when you explicitly pass `--apply`

## Current Scope

This repo does not yet fetch confirmed MLB starting lineups from a separate provider, so the optimizer only acts on starting-status fields if they are present in the roster payload or when you inject manual scenario data in the notebook.

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy the env template:

```bash
cp .env.example .env
```

4. Fill in your Yahoo app credentials and team key in `.env`.
5. Capture your initial refresh token:

```bash
python auth.py
```

6. Run a dry-run roster check:

```bash
python main.py --date 2026-03-17
```

7. Apply proposed roster changes only after you trust the output:

```bash
python main.py --date 2026-03-17 --apply
```

## Files

- [`main.py`](/Users/fasky/Workspace/yahoo-fantasy-agent/main.py): CLI entry point
- [`auth.py`](/Users/fasky/Workspace/yahoo-fantasy-agent/auth.py): initial OAuth capture and token refresh helpers
- [`yahoo_api.py`](/Users/fasky/Workspace/yahoo-fantasy-agent/yahoo_api.py): Yahoo Fantasy API client and XML parsing
- [`mlb_lineups.py`](/Users/fasky/Workspace/yahoo-fantasy-agent/mlb_lineups.py): MLB schedule and starting-status enrichment
- [`lineup.py`](/Users/fasky/Workspace/yahoo-fantasy-agent/lineup.py): conservative lineup optimization logic
- [`models.py`](/Users/fasky/Workspace/yahoo-fantasy-agent/models.py): shared data models
- [`data/yahoo_mlb_id_map.csv`](/Users/fasky/Workspace/yahoo-fantasy-agent/data/yahoo_mlb_id_map.csv): local Yahoo-to-MLB player ID crosswalk
- [`data/yahoo_mlb_id_map_sfbb.csv`](/Users/fasky/Workspace/yahoo-fantasy-agent/data/yahoo_mlb_id_map_sfbb.csv): normalized SFBB Yahoo-to-MLB crosswalk
- [`notebooks/manual_lineup_scenario.ipynb`](/Users/fasky/Workspace/yahoo-fantasy-agent/notebooks/manual_lineup_scenario.ipynb): manual scenario notebook
- [`notebooks/live_lineup_workflow.ipynb`](/Users/fasky/Workspace/yahoo-fantasy-agent/notebooks/live_lineup_workflow.ipynb): live Yahoo fetch + starting-status workflow

## Next Build Steps

- add a reliable starting-lineups/projections source
- add tests for XML parsing and optimizer behavior

## GitHub Actions Automation

The repo now includes a scheduled workflow at [`.github/workflows/daily.yml`](/Users/fasky/Workspace/yahoo-fantasy-agent/.github/workflows/daily.yml).

Behavior:

- scheduled runs poll every 30 minutes
- the app only acts when the current local time is 30 minutes before a unique rounded start block for that day
- start times are grouped by hour, so `4:00`, `4:05`, and `4:07` all map to the `4:00 PM` block and trigger a `3:30 PM` run
- scheduled runs are dry-run only
- manual `workflow_dispatch` runs can either dry-run or apply changes, and can force an immediate run
- each triggered run can send an email report
- the workflow uses the same MLB enrichment path as the notebook and CLI
- the workflow resolves `YAHOO_LINEUP_DATE` in `America/Los_Angeles`

Add these GitHub repository secrets before enabling it:

- `YAHOO_CLIENT_ID`
- `YAHOO_CLIENT_SECRET`
- `YAHOO_REFRESH_TOKEN`
- `YAHOO_TEAM_KEY`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM`
- `SMTP_TO`

Recommended rollout:

1. let scheduled dry-runs run for a few days
2. review the emailed reports and Actions logs against your live roster
3. use manual dispatch with `apply_changes=true` only after the output looks trustworthy

You can still run the same path locally with:

```bash
python main.py
python main.py --apply
python automation.py --force --email
```

## Local ID Crosswalk

The MLB matcher now prefers the normalized SFBB Yahoo-to-MLB crosswalk and then your local overrides before falling back to name matching. Fill in [`data/yahoo_mlb_id_map.csv`](/Users/fasky/Workspace/yahoo-fantasy-agent/data/yahoo_mlb_id_map.csv) with `mlb_person_id` values to eliminate any remaining `player_unmapped` cases on live runs.

You can refresh the normalized SFBB crosswalk with:

```bash
python /Users/fasky/Workspace/yahoo-fantasy-agent/import_sfbb_player_id_map.py
```
