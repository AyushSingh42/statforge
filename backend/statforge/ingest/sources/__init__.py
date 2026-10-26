"""Registry of data sources. Add the chosen provider to SOURCES to make it selectable.

The active source is chosen with --source on the CLI or the
STATFORGE_DATA_SOURCE environment variable (default: "fixture").
"""

from collections.abc import Callable

from statforge.config import DATA_DIR
from statforge.ingest.fields import FIELD_NAMES
from statforge.ingest.sources.base import DataSource, RawRow, SourceInfo
from statforge.ingest.sources.csv_source import CsvSource


def fixture_source() -> DataSource:
    """Small synthetic dataset for tests, CI and frontend work without network access."""
    return CsvSource(
        info=SourceInfo(
            name="fixture",
            attribution="StatForge synthetic fixture (not real NFL data)",
            url="",
            version="fixture-1",
        ),
        path=DATA_DIR / "fixtures" / "player_seasons_sample.csv",
        column_map={name: name for name in FIELD_NAMES},
    )


SOURCES: dict[str, Callable[[], DataSource]] = {
    "fixture": fixture_source,
    # "nflverse": NflverseSource,  # <- register the chosen provider here
}


class UnknownSourceError(KeyError):
    pass


def get_source(name: str) -> DataSource:
    try:
        factory = SOURCES[name]
    except KeyError:
        known = ", ".join(sorted(SOURCES))
        raise UnknownSourceError(f"Unknown data source {name!r}; known sources: {known}") from None
    return factory()


__all__ = [
    "SOURCES",
    "CsvSource",
    "DataSource",
    "RawRow",
    "SourceInfo",
    "UnknownSourceError",
    "get_source",
]
