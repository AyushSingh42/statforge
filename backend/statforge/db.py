"""SQLite schema for the imported snapshot, and how the API opens it.

The importer is the only writer. It builds a complete database and swaps it into
place, so the API only ever opens a finished snapshot, read-only.
"""

import sqlite3
from pathlib import Path

from statforge.config import SUPPORTED_POSITIONS
from statforge.ingest.fields import STAT_FIELD_NAMES

SCHEMA_VERSION = 1

# NUMERIC keeps whole counts as integers and fractional values (e.g. games) as reals.
_STAT_COLUMNS = ",\n    ".join(f"{name} NUMERIC" for name in STAT_FIELD_NAMES)
_POSITIONS = ", ".join(f"'{p}'" for p in SUPPORTED_POSITIONS)

SCHEMA = f"""
CREATE TABLE dataset_metadata (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    schema_version INTEGER NOT NULL,
    dataset_version TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_attribution TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_version TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    first_season INTEGER NOT NULL,
    last_season INTEGER NOT NULL,
    player_season_count INTEGER NOT NULL,
    merged_row_count INTEGER NOT NULL
);

CREATE TABLE field_definitions (
    name TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    definition TEXT NOT NULL,
    unit TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('identity', 'stat')),
    sort_order INTEGER NOT NULL
);

CREATE TABLE players (
    player_id TEXT PRIMARY KEY,
    player_name TEXT NOT NULL
);

CREATE TABLE player_seasons (
    player_id TEXT NOT NULL REFERENCES players (player_id),
    season INTEGER NOT NULL,
    position TEXT NOT NULL CHECK (position IN ({_POSITIONS})),
    {_STAT_COLUMNS},
    PRIMARY KEY (player_id, season)
);

CREATE INDEX player_seasons_by_season_position ON player_seasons (season, position);
"""


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def connect(path: Path) -> sqlite3.Connection:
    """Open an imported snapshot read-only, with rows usable as dict(row)."""
    if not path.is_file():
        raise FileNotFoundError(f"No database at {path}. Run: python -m statforge.ingest.importer")
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn
