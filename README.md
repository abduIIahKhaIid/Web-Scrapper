# Web Scrapper

A Python project for loading consolidated data, fetching Meydan API activities, and running reconciliation for a jurisdiction.

## Prerequisites

- Python 3.12 or later
- `uv` installed and configured for your environment
- `poetry` available via `uv` or installed globally

## Setup

Open a terminal in the project root and run:

```bash
cd /workspaces/Web-Scrapper
uv poetry install
```

If you prefer to use an interactive shell, you can also run:

```bash
uv poetry shell
```

## Run the project

Run the project commands from the repository root.

### 1. Load consolidated data

```bash
uv run python scripts/load_consolidated.py --jurisdiction Meydan
```

### 2. Fetch Meydan API activities

```bash
uv run python scripts/fetch_meydan_api.py
```

### 3. Run reconciliation (dry run)

```bash
uv run python scripts/run_reconciliation.py --jurisdiction Meydan --fetched-csv data/fetched/meydan_api_activities.csv
```

### 4. Run reconciliation and apply changes

```bash
uv run python scripts/run_reconciliation.py --jurisdiction Meydan --fetched-csv data/fetched/meydan_api_activities.csv --apply
```

## Notes

- Ensure any required environment variables or configuration files are set before running the commands.
- Use the `--jurisdiction Meydan` flag to target the Meydan jurisdiction.
- The `--apply` flag enables write/apply mode for reconciliation.
