"""Template for a new data source. Copy this file, fill in the TODOs, register it.

Steps:
  1. Copy to statforge/ingest/sources/<name>.py and rename the class.
  2. Fill in INFO and COLUMN_MAP (right-hand side = the provider's column names).
  3. Implement fetch(): return regular-season, one-row-per-player-season data.
  4. Add one line to SOURCES in statforge/ingest/sources/__init__.py.
  5. Run: python -m statforge.ingest.verify --source <name>

If the provider ships a CSV you can download once, you may not need a new
class at all: register a CsvSource pointing at the file (see fixture_source).
"""

from collections.abc import Iterable, Sequence

from statforge.ingest.sources.base import DataSource, RawRow, SourceInfo

INFO = SourceInfo(
    name="template",  # TODO: registry name, e.g. "nflverse"
    attribution="TODO: provider name and licence",
    url="TODO: https://...",
    version="TODO: release tag or retrieval date",
)

# TODO: replace each right-hand side with the provider's column name.
COLUMN_MAP: dict[str, str] = {
    "player_id": "player_id",
    "player_name": "player_name",
    "position": "position",
    "season": "season",
    "games": "games",
    "pass_attempts": "pass_attempts",
    "pass_yards": "pass_yards",
    "pass_td": "pass_td",
    "interceptions": "interceptions",
    "carries": "carries",
    "rush_yards": "rush_yards",
    "receptions": "receptions",
    "targets": "targets",
    "rec_yards": "rec_yards",
}


class TemplateSource(DataSource):
    info = INFO
    column_map = COLUMN_MAP

    def fetch(self, seasons: Sequence[int]) -> Iterable[RawRow]:
        # TODO: load the provider's player-season summaries for `seasons`,
        # drop postseason rows, and yield one mapping per row. If the provider
        # returns one row per player-team, either sum them here or leave that
        # to the importer (traded-player reconciliation is a Week 2 task).
        raise NotImplementedError("Fill in TemplateSource.fetch for the chosen provider")
