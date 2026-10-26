"""A source backed by a local CSV file, used for fixtures and offline snapshots."""

import csv
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

from statforge.ingest.sources.base import DataSource, RawRow, SourceInfo


class CsvSource(DataSource):
    def __init__(
        self,
        info: SourceInfo,
        path: Path,
        column_map: Mapping[str, str],
        season_column: str | None = None,
    ) -> None:
        self.info = info
        self.path = path
        self.column_map = column_map
        self._season_column = season_column or column_map.get("season", "season")

    def fetch(self, seasons: Sequence[int]) -> Iterator[RawRow]:
        wanted = {str(s) for s in seasons}
        with self.path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row.get(self._season_column) in wanted:
                    yield row
