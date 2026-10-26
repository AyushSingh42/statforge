import pytest

from statforge.ingest.fields import FIELD_NAMES, STAT_FIELD_NAMES
from statforge.ingest.normalize import RowError, SchemaError, normalize_row

IDENTITY_MAP = {name: name for name in FIELD_NAMES}


def raw_row(**overrides):
    row = {name: "0" for name in STAT_FIELD_NAMES}
    row.update(player_id="P1", player_name="Some Player", position="qb", season="2020")
    row.update(overrides)
    return row


def test_field_names_are_unique():
    assert len(FIELD_NAMES) == len(set(FIELD_NAMES))


def test_coerces_types_and_uppercases_position():
    row = normalize_row(raw_row(pass_yards="3000", games="16.0"), IDENTITY_MAP)
    assert row["position"] == "QB"
    assert row["season"] == 2020
    assert row["pass_yards"] == 3000 and isinstance(row["pass_yards"], int)
    assert row["games"] == 16


def test_renames_source_columns():
    column_map = {**IDENTITY_MAP, "pass_yards": "passing_yards"}
    raw = raw_row()
    raw["passing_yards"] = raw.pop("pass_yards")
    raw["passing_yards"] = "250"
    assert normalize_row(raw, column_map)["pass_yards"] == 250


@pytest.mark.parametrize("blank", ["", "NA", None, float("nan")])
def test_missing_stats_become_none_not_zero(blank):
    assert normalize_row(raw_row(targets=blank), IDENTITY_MAP)["targets"] is None


def test_fractional_values_are_kept():
    assert normalize_row(raw_row(games="8.5"), IDENTITY_MAP)["games"] == 8.5


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"pass_yards": "lots"}, "pass_yards"),
        ({"pass_yards": "inf"}, "not finite"),
        ({"season": "2020.5"}, "season"),
        ({"player_id": " "}, "player_id is blank"),
    ],
)
def test_bad_values_raise_row_error(overrides, message):
    with pytest.raises(RowError, match=message):
        normalize_row(raw_row(**overrides), IDENTITY_MAP)


def test_incomplete_column_map_raises_schema_error():
    column_map = {k: v for k, v in IDENTITY_MAP.items() if k != "targets"}
    with pytest.raises(SchemaError, match="targets"):
        normalize_row(raw_row(), column_map)


def test_missing_source_column_raises_schema_error():
    raw = raw_row()
    del raw["rec_yards"]
    with pytest.raises(SchemaError, match="rec_yards"):
        normalize_row(raw, IDENTITY_MAP)
