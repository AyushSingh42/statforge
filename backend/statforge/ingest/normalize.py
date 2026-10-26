"""Map a source's rows onto canonical fields and coerce their types."""

import math
from collections.abc import Mapping
from typing import Any

from statforge.ingest.fields import FIELD_NAMES, STAT_FIELD_NAMES
from statforge.ingest.sources.base import RawRow

NormalizedRow = dict[str, Any]


class SchemaError(ValueError):
    """The source's columns don't line up with the canonical fields."""


class RowError(ValueError):
    """A single row has a value that can't be coerced."""


def missing_mappings(column_map: Mapping[str, str]) -> list[str]:
    """Canonical fields the source has not mapped."""
    return [name for name in FIELD_NAMES if name not in column_map]


def missing_columns(column_map: Mapping[str, str], raw: RawRow) -> list[str]:
    """Mapped source columns that are absent from a raw row."""
    return [col for col in column_map.values() if col not in raw]


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return isinstance(value, str) and value.strip() in ("", "NA", "NaN")


def _to_number(value: Any, field: str) -> int | float | None:
    if _is_blank(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise RowError(f"{field}: {value!r} is not a number") from None
    if not math.isfinite(number):
        raise RowError(f"{field}: {value!r} is not finite")
    return int(number) if number.is_integer() else number


def normalize_row(raw: RawRow, column_map: Mapping[str, str]) -> NormalizedRow:
    """Rename and coerce one row. Missing stats become None, never zero (R3)."""
    if gaps := missing_mappings(column_map):
        raise SchemaError(f"column_map has no entry for: {', '.join(gaps)}")
    if gaps := missing_columns(column_map, raw):
        raise SchemaError(f"source row is missing columns: {', '.join(gaps)}")

    row: NormalizedRow = {}
    for name in ("player_id", "player_name", "position"):
        value = raw[column_map[name]]
        if _is_blank(value):
            raise RowError(f"{name} is blank")
        row[name] = str(value).strip()
    row["position"] = row["position"].upper()

    season = _to_number(raw[column_map["season"]], "season")
    if not isinstance(season, int):
        raise RowError(f"season: {raw[column_map['season']]!r} is not a whole year")
    row["season"] = season

    for name in STAT_FIELD_NAMES:
        row[name] = _to_number(raw[column_map[name]], name)
    return row
