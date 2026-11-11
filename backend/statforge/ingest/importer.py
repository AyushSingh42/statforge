"""Import a verified data source into the SQLite snapshot the API reads.

    python -m statforge.ingest.importer --source nflverse --seasons 2016-2025

The source is verified first; nothing is written unless it covers the requested
scope. The database is rebuilt from scratch in a temporary file and swapped into
place, so re-running an import never adds rows and a failed import leaves the
previous snapshot untouched. Exits 0 on success, 1 on failure, 2 on bad arguments.
"""

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from collections.abc import Iterable, Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from statforge.config import (
    SUPPORTED_POSITIONS,
    SUPPORTED_SEASONS,
    data_source_name,
    database_path,
)
from statforge.db import SCHEMA_VERSION, create_schema
from statforge.ingest.fields import ALL_FIELDS, STAT_FIELD_NAMES
from statforge.ingest.normalize import NormalizedRow, normalize_row
from statforge.ingest.sources import DataSource, UnknownSourceError, get_source
from statforge.ingest.verify import parse_seasons, verify_source


class ImportFailedError(RuntimeError):
    """The source did not pass verification; the existing database was not changed."""


@dataclass(frozen=True)
class ImportSummary:
    path: Path
    dataset_version: str
    player_seasons: int
    players: int
    merged_rows: int


def _add_stat(total: int | float | None, value: int | float | None) -> int | float | None:
    # A missing stint makes the season total unknown; never treat it as zero (R3).
    return None if total is None or value is None else total + value


def merge_stints(rows: Iterable[NormalizedRow]) -> tuple[list[NormalizedRow], int]:
    """Combine repeated player-season rows (e.g. traded players) into season totals.

    Returns the merged rows sorted by (season, player_id) and how many rows were
    folded into an earlier one. Identity fields come from the first row seen.
    """
    merged: dict[tuple[str, int], NormalizedRow] = {}
    folded = 0
    for row in rows:
        key = (row["player_id"], row["season"])
        if (existing := merged.get(key)) is None:
            merged[key] = dict(row)
            continue
        folded += 1
        for name in STAT_FIELD_NAMES:
            existing[name] = _add_stat(existing[name], row[name])
    return [merged[key] for key in sorted(merged, key=lambda k: (k[1], k[0]))], folded


def dataset_version(source: DataSource, rows: Sequence[NormalizedRow]) -> str:
    """Content-derived version: the same snapshot always imports to the same version."""
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    return f"{source.info.name}-{digest[:12]}"


def _write(
    conn: sqlite3.Connection,
    source: DataSource,
    seasons: Sequence[int],
    rows: Sequence[NormalizedRow],
    version: str,
    merged_rows: int,
) -> None:
    create_schema(conn)
    conn.executemany(
        "INSERT INTO field_definitions VALUES (?, ?, ?, ?, ?, ?)",
        [(f.name, f.label, f.definition, f.unit, f.kind, i) for i, f in enumerate(ALL_FIELDS)],
    )
    # Rows are sorted by season, so the last name seen is the player's most recent.
    names = {row["player_id"]: row["player_name"] for row in rows}
    conn.executemany("INSERT INTO players VALUES (?, ?)", sorted(names.items()))
    columns = ("player_id", "season", "position", *STAT_FIELD_NAMES)
    conn.executemany(
        f"INSERT INTO player_seasons ({', '.join(columns)}) "
        f"VALUES ({', '.join('?' * len(columns))})",
        [tuple(row[c] for c in columns) for row in rows],
    )
    conn.execute(
        "INSERT INTO dataset_metadata VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            SCHEMA_VERSION,
            version,
            source.info.name,
            source.info.attribution,
            source.info.url,
            source.info.version,
            datetime.now(UTC).isoformat(timespec="seconds"),
            min(seasons),
            max(seasons),
            len(rows),
            merged_rows,
        ),
    )


def import_source(source: DataSource, seasons: Sequence[int], path: Path) -> ImportSummary:
    report = verify_source(source, seasons)
    if not report.ok:
        raise ImportFailedError(report.format())

    normalized = (normalize_row(raw, source.column_map) for raw in source.fetch(seasons))
    rows, merged_rows = merge_stints(
        row for row in normalized if row["position"] in SUPPORTED_POSITIONS
    )
    version = dataset_version(source, rows)

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.unlink(missing_ok=True)
    try:
        with closing(sqlite3.connect(tmp_path)) as conn, conn:
            _write(conn, source, seasons, rows, version, merged_rows)
        os.replace(tmp_path, path)
    finally:
        tmp_path.unlink(missing_ok=True)

    return ImportSummary(
        path=path,
        dataset_version=version,
        player_seasons=len(rows),
        players=len({row["player_id"] for row in rows}),
        merged_rows=merged_rows,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--source", default=data_source_name(), help="registered source name")
    parser.add_argument(
        "--seasons",
        type=parse_seasons,
        default=SUPPORTED_SEASONS,
        help="e.g. 2016-2025 (default: the supported range)",
    )
    parser.add_argument("--db", type=Path, default=database_path(), help="output SQLite file")
    args = parser.parse_args(argv)

    try:
        source = get_source(args.source)
    except UnknownSourceError as exc:
        print(exc.args[0], file=sys.stderr)
        return 2

    try:
        summary = import_source(source, args.seasons, args.db)
    except (ImportFailedError, FileNotFoundError) as exc:
        print(f"Import failed; {args.db} was not changed.\n\n{exc}", file=sys.stderr)
        return 1

    print(
        f"Imported {summary.player_seasons} player-seasons ({summary.players} players, "
        f"{summary.merged_rows} traded-player rows merged) into {summary.path}\n"
        f"Dataset version: {summary.dataset_version}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
