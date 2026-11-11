"""Local snapshots of nflverse regular-season player statistics.

The downloader deliberately lives outside this source.  Fetching data for the
app should be repeatable and must not make an unannounced network request; run
``python -m statforge.ingest.download_nflverse`` to create or refresh a local
snapshot instead.
"""

import csv
import json
from collections.abc import Iterator, Sequence
from pathlib import Path

from statforge.config import DATA_DIR
from statforge.ingest.sources.base import DataSource, RawRow, SourceInfo

SNAPSHOT_DIR = DATA_DIR / "nflverse"
MANIFEST_NAME = "manifest.json"
RELEASE_URL = "https://github.com/nflverse/nflverse-data/releases/tag/stats_player"
FILE_NAME_TEMPLATE = "stats_player_reg_{season}.csv"

COLUMN_MAP = {
    "player_id": "player_id",
    "player_name": "player_display_name",
    "position": "position",
    "season": "season",
    "games": "games",
    "pass_attempts": "attempts",
    "pass_yards": "passing_yards",
    "pass_td": "passing_tds",
    "interceptions": "passing_interceptions",
    "carries": "carries",
    "rush_yards": "rushing_yards",
    "receptions": "receptions",
    "targets": "targets",
    "rec_yards": "receiving_yards",
}


class NflverseSource(DataSource):
    """Read pinned nflverse CSV files containing player-season totals."""

    column_map = COLUMN_MAP

    def __init__(self, snapshot_dir: Path = SNAPSHOT_DIR) -> None:
        self.snapshot_dir = snapshot_dir
        self.info = SourceInfo(
            name="nflverse",
            attribution="nflverse player statistics (CC BY 4.0; see release metadata)",
            url=RELEASE_URL,
            version=self._snapshot_version(),
        )

    def _snapshot_version(self) -> str:
        manifest = self.snapshot_dir / MANIFEST_NAME
        try:
            with manifest.open(encoding="utf-8") as fh:
                retrieved_at = json.load(fh).get("retrieved_at")
        except (FileNotFoundError, OSError, ValueError, AttributeError):
            retrieved_at = None
        return f"local snapshot retrieved {retrieved_at}" if retrieved_at else "local CSV snapshot"

    def _path_for(self, season: int) -> Path:
        return self.snapshot_dir / FILE_NAME_TEMPLATE.format(season=season)

    def fetch(self, seasons: Sequence[int]) -> Iterator[RawRow]:
        for season in dict.fromkeys(seasons):
            path = self._path_for(season)
            if not path.is_file():
                raise FileNotFoundError(
                    f"nflverse snapshot for {season} is missing at {path}. "
                    "Run: python -m statforge.ingest.download_nflverse"
                )
            with path.open(newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    # Release files occasionally end with a team aggregate row
                    # that has no player ID. It is not a player-season record.
                    if row.get("season_type") == "REG" and row.get("player_id"):
                        yield row
