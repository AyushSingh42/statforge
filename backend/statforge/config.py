"""Settings shared by the API and the ingestion tools."""

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"

# Core release scope (proposal section 2).
FIRST_SEASON = 2016
LAST_SEASON = 2025
SUPPORTED_SEASONS: tuple[int, ...] = tuple(range(FIRST_SEASON, LAST_SEASON + 1))
SUPPORTED_POSITIONS: tuple[str, ...] = ("QB", "RB", "WR", "TE")


def data_source_name() -> str:
    """Registry name of the active data source; see statforge.ingest.sources."""
    return os.environ.get("STATFORGE_DATA_SOURCE", "fixture")
