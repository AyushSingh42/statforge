# StatForge backend

Data ingestion, SQLite storage (Week 2) and the FastAPI app.

## Setup

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                      # tests + coverage (fails under 80%)
ruff check . && ruff format --check .
uvicorn statforge.api.main:app --reload   # GET /health
```

## Data sources

Every provider is wrapped in a `DataSource` (`statforge/ingest/sources/base.py`) that declares:

- `info`: name, attribution, URL and version, all recorded with the snapshot
- `column_map`: our canonical field name -> the provider's column name (fields are listed in `statforge/ingest/fields.py`)
- `fetch(seasons)`: yields the provider's regular-season player-season rows

Normalisation, type checks and coverage checks are shared, so a new source only needs those three things.

### Adding the chosen source

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
