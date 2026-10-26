"""The contract every historical data source implements.

A source only says where its rows come from and how its column names map onto
ours (statforge.ingest.fields). Type coercion and validation live in
statforge.ingest.normalize so every source is checked the same way.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

RawRow = Mapping[str, Any]


@dataclass(frozen=True)
class SourceInfo:
    """Attribution recorded with every snapshot and shown to users."""

    name: str
    attribution: str
    url: str
    version: str


class DataSource(ABC):
    info: SourceInfo
    # Canonical field name -> this source's column name. Must cover every
    # name in statforge.ingest.fields.FIELD_NAMES.
    column_map: Mapping[str, str]

    @abstractmethod
    def fetch(self, seasons: Sequence[int]) -> Iterable[RawRow]:
        """Yield regular-season player-season rows for the requested seasons.

        Rows use the source's own column names. Filtering out postseason rows
        is the source's job; position filtering and type checks are not.
        """
