"""Check that a data source covers the seasons, positions and fields we need.

    python -m statforge.ingest.verify --source fixture --seasons 2016-2025

Exits 0 when the source is usable, 1 when it is not, 2 on bad arguments.
"""

import argparse
import sys
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field

from statforge.config import SUPPORTED_POSITIONS, SUPPORTED_SEASONS, data_source_name
from statforge.ingest.fields import STAT_FIELD_NAMES
from statforge.ingest.normalize import (
    RowError,
    missing_columns,
    missing_mappings,
    normalize_row,
)
from statforge.ingest.sources import DataSource, UnknownSourceError, get_source

MAX_LISTED_ROW_ERRORS = 10


@dataclass
class VerificationReport:
    source_name: str
    source_version: str
    seasons: tuple[int, ...]
    rows_read: int = 0
    rows_per_season: Counter[int] = field(default_factory=Counter)
    positions_per_season: dict[int, Counter[str]] = field(
        default_factory=lambda: defaultdict(Counter)
    )
    missing_values: Counter[str] = field(default_factory=Counter)
    duplicate_player_seasons: int = 0
    row_errors: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def format(self) -> str:
        lines = [
            f"Source: {self.source_name} ({self.source_version})",
            f"Seasons requested: {', '.join(map(str, self.seasons))}",
            f"Rows read: {self.rows_read}",
            "",
            "Season  Rows  " + "  ".join(f"{p:>4}" for p in SUPPORTED_POSITIONS),
        ]
        for season in self.seasons:
            counts = self.positions_per_season.get(season, Counter())
            cells = "  ".join(f"{counts[p]:>4}" for p in SUPPORTED_POSITIONS)
            lines.append(f"{season:<6}  {self.rows_per_season[season]:>4}  {cells}")
        if self.missing_values:
            lines += ["", "Missing values (kept as unavailable, not zero):"]
            lines += [f"  {name}: {n}" for name, n in sorted(self.missing_values.items())]
        if self.duplicate_player_seasons:
            lines += [
                "",
                f"Note: {self.duplicate_player_seasons} repeated player-season rows "
                "(e.g. traded players); the importer must combine them.",
            ]
        if self.row_errors:
            lines += ["", "Row errors (first few):"] + [f"  {e}" for e in self.row_errors]
        lines += ["", "Problems:" if self.problems else "OK: source covers the required scope."]
        lines += [f"  - {p}" for p in self.problems]
        return "\n".join(lines)


def verify_source(source: DataSource, seasons: Sequence[int]) -> VerificationReport:
    report = VerificationReport(
        source_name=source.info.name,
        source_version=source.info.version,
        seasons=tuple(seasons),
    )
    if gaps := missing_mappings(source.column_map):
        report.problems.append(f"column_map has no entry for: {', '.join(gaps)}")
        return report

    wanted = set(seasons)
    seen: Counter[tuple[str, int]] = Counter()
    error_count = 0
    for raw in source.fetch(seasons):
        report.rows_read += 1
        if report.rows_read == 1 and (gaps := missing_columns(source.column_map, raw)):
            report.problems.append(f"source rows are missing columns: {', '.join(gaps)}")
            return report
        try:
            row = normalize_row(raw, source.column_map)
        except RowError as exc:
            error_count += 1
            if len(report.row_errors) < MAX_LISTED_ROW_ERRORS:
                report.row_errors.append(f"row {report.rows_read}: {exc}")
            continue
        season = row["season"]
        if season not in wanted:
            report.problems.append(f"fetch returned unrequested season {season}")
            continue
        if row["position"] not in SUPPORTED_POSITIONS:
            continue
        report.rows_per_season[season] += 1
        report.positions_per_season[season][row["position"]] += 1
        seen[(row["player_id"], season)] += 1
        for name in STAT_FIELD_NAMES:
            if row[name] is None:
                report.missing_values[name] += 1

    report.duplicate_player_seasons = sum(n - 1 for n in seen.values() if n > 1)
    if error_count:
        report.problems.append(f"{error_count} rows could not be parsed")
    if report.rows_read == 0:
        report.problems.append("source returned no rows")
    for season in seasons:
        counts = report.positions_per_season.get(season, Counter())
        if absent := [p for p in SUPPORTED_POSITIONS if not counts[p]]:
            report.problems.append(f"season {season} has no {'/'.join(absent)} rows")
    return report


def parse_seasons(text: str) -> tuple[int, ...]:
    """Accept "2016-2025", "2019" or "2016,2018,2020"."""
    try:
        if "-" in text:
            start, end = (int(part) for part in text.split("-", 1))
            if end < start:
                raise ValueError
            return tuple(range(start, end + 1))
        return tuple(int(part) for part in text.split(","))
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid season range: {text!r}") from None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--source", default=data_source_name(), help="registered source name")
    parser.add_argument(
        "--seasons",
        type=parse_seasons,
        default=SUPPORTED_SEASONS,
        help="e.g. 2016-2025 (default: the supported range)",
    )
    args = parser.parse_args(argv)

    try:
        source = get_source(args.source)
    except UnknownSourceError as exc:
        print(exc.args[0], file=sys.stderr)
        return 2

    report = verify_source(source, args.seasons)
    print(report.format())
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
