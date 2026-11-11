# StatForge backend

Data ingestion, SQLite storage and the FastAPI app.

## Setup

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                      # tests + coverage (fails under 80%)
ruff check . && ruff format --check .
uvicorn statforge.api.main:app --reload   # needs an imported database, see below
```

## API

All data endpoints read the SQLite snapshot (`STATFORGE_DB_PATH`) and return 503 with
setup instructions if it hasn't been imported yet.

| Endpoint | Returns |
|---|---|
| `GET /health` | Status, version and configured data source. |
| `GET /fields` | The field dictionary (name, label, definition, unit) and dataset version. |
| `GET /seasons` | Imported seasons and positions, plus source attribution and dataset version. |
| `POST /evaluate` | Calculations for the requested seasons, positions and minimums. |

`POST /evaluate` follows [Docs/evaluate-contract.md](../Docs/evaluate-contract.md): seasons and
positions are filtered in SQL with bound parameters, minimums are inclusive and combined with
AND, and invalid formulas return a structured 422. Records are not yet ranked
(`"stage": "calculation_only"`).

## Data sources

Every provider is wrapped in a `DataSource` (`statforge/ingest/sources/base.py`) that declares:

- `info`: name, attribution, URL and version, all recorded with the snapshot
- `column_map`: our canonical field name -> the provider's column name (fields are listed in `statforge/ingest/fields.py`)
- `fetch(seasons)`: yields the provider's regular-season player-season rows

Normalisation, type checks and coverage checks are shared, so a new source only needs those three things.

### nflverse snapshot

`nflverse` is the initial production source. It reads a local snapshot rather
than making live network requests during application use or verification.
Download the supported history once (or use `--force` to refresh it):

```bash
python -m statforge.ingest.download_nflverse
python -m statforge.ingest.verify --source nflverse
```

The CSVs are ignored by Git; `data/nflverse/manifest.json` records the retrieval
time, source URLs, and SHA-256 checksums so a snapshot can be audited or
recreated. It is the default source; set `STATFORGE_DATA_SOURCE=fixture` for
the synthetic test data. nflverse data is attributed in source metadata; check
the relevant release metadata before a new kind of data is added.

## SQLite snapshot

The importer verifies a source, then writes `data/statforge.sqlite3` (override with
`--db` or `STATFORGE_DB_PATH`). The API reads this file read-only through `statforge.db.connect`.

```bash
python -m statforge.ingest.importer                       # nflverse, 2016-2025
python -m statforge.ingest.importer --source fixture      # synthetic data, no download
```

Tables: `player_seasons` (one row per player per season, canonical field names),
`players`, `field_definitions` (the R1 dictionary) and `dataset_metadata` (source,
attribution, retrieval version, import time and a content-derived `dataset_version`).

- Each run rebuilds the database in a temp file and swaps it in, so re-importing never
  adds rows and a failed import leaves the previous snapshot in place.
- Repeated rows for a player-season (traded players) are summed. If any stint is
  missing a stat, the season total is stored as NULL rather than a partial sum.
- Rows outside QB/RB/WR/TE are skipped.

### Adding another source

1. Copy `statforge/ingest/sources/template.py` to `statforge/ingest/sources/<name>.py` and fill in the TODOs.
   If the provider publishes a CSV, you can register a `CsvSource` with a `column_map` instead of writing a class.
2. Register it in `SOURCES` in `statforge/ingest/sources/__init__.py`.
3. Verify it covers 2016–2025 for QB/RB/WR/TE:

   ```bash
   python -m statforge.ingest.verify --source <name>            # default seasons 2016-2025
   python -m statforge.ingest.verify --source <name> --seasons 2019
   ```

   Exit code 0 means usable, 1 lists the problems, 2 means bad arguments.
4. Select it with `STATFORGE_DATA_SOURCE=<name>` (default: `fixture`).

The `fixture` source (`data/fixtures/player_seasons_sample.csv`) is synthetic data used by tests and CI, which never call a live sports API.
Its `FX-QB-01` rows match the proposal's worked example (QB Score = 7.75).
