import csv
import io

import pytest

from statforge.config import SUPPORTED_SEASONS
from statforge.ingest.fields import FIELD_NAMES
from statforge.ingest.sources import CsvSource, SourceInfo, get_source
from statforge.ingest.verify import main, parse_seasons, verify_source

INFO = SourceInfo(name="test", attribution="test", url="", version="t1")


def write_source(tmp_path, rows, header=FIELD_NAMES, column_map=None):
    path = tmp_path / "rows.csv"
    with path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)
    return CsvSource(INFO, path, column_map or {name: name for name in FIELD_NAMES})


def full_season(season, player_prefix="P"):
    stats = ["1"] * (len(FIELD_NAMES) - 4)
    return [
        [f"{player_prefix}{pos}", f"Player {pos}", pos, season, *stats]
        for pos in ["QB", "RB", "WR", "TE"]
    ]


def test_fixture_covers_supported_scope():
    report = verify_source(get_source("fixture"), SUPPORTED_SEASONS)
    assert report.ok, report.problems
    assert report.rows_per_season[2016] == 8
    assert report.missing_values["targets"] == len(SUPPORTED_SEASONS)


def test_missing_season_and_position_are_problems(tmp_path):
    rows = full_season(2020) + [r for r in full_season(2021) if r[2] != "TE"]
    report = verify_source(write_source(tmp_path, rows), [2020, 2021, 2022])
    assert not report.ok
    assert "season 2021 has no TE rows" in report.problems
    assert "season 2022 has no QB/RB/WR/TE rows" in report.problems


def test_renamed_column_without_mapping_is_a_schema_problem(tmp_path):
    header = [("passing_yards" if f == "pass_yards" else f) for f in FIELD_NAMES]
    report = verify_source(write_source(tmp_path, full_season(2020), header), [2020])
    assert report.problems == ["source rows are missing columns: pass_yards"]


def test_incomplete_column_map_is_reported(tmp_path):
    column_map = {name: name for name in FIELD_NAMES if name != "games"}
    report = verify_source(write_source(tmp_path, [], column_map=column_map), [2020])
    assert report.problems == ["column_map has no entry for: games"]


def test_unparseable_rows_and_duplicates_are_reported(tmp_path):
    bad = full_season(2020)[0][:]
    bad[FIELD_NAMES.index("pass_yards")] = "lots"
    traded = full_season(2020)[1]
    other = ["X1", "Kicker", "K", 2020] + ["1"] * (len(FIELD_NAMES) - 4)
    rows = full_season(2020) + [bad, traded, other]
    report = verify_source(write_source(tmp_path, rows), [2020])
    assert "1 rows could not be parsed" in report.problems
    assert report.duplicate_player_seasons == 1
    assert report.rows_per_season[2020] == 5
    assert "Row errors" in report.format()
    assert "traded players" in report.format()


def test_empty_source_is_a_problem(tmp_path):
    report = verify_source(write_source(tmp_path, []), [2020])
    assert "source returned no rows" in report.problems


def test_unrequested_season_is_a_problem():
    class Leaky(CsvSource):
        def fetch(self, seasons):
            yield from csv.DictReader(
                io.StringIO(",".join(FIELD_NAMES) + "\nP,Q,QB,1999" + ",1" * 10)
            )

    source = Leaky(INFO, None, {name: name for name in FIELD_NAMES})
    report = verify_source(source, [2020])
    assert "fetch returned unrequested season 1999" in report.problems


@pytest.mark.parametrize(
    "text, expected",
    [("2016-2018", (2016, 2017, 2018)), ("2019", (2019,)), ("2016,2020", (2016, 2020))],
)
def test_parse_seasons(text, expected):
    assert parse_seasons(text) == expected


@pytest.mark.parametrize("text", ["2020-2016", "abc", "2016-"])
def test_parse_seasons_rejects_bad_input(text):
    with pytest.raises(Exception, match="invalid season range"):
        parse_seasons(text)


def test_cli_exit_codes(capsys):
    assert main(["--source", "fixture"]) == 0
    assert "OK: source covers the required scope." in capsys.readouterr().out
    assert main(["--source", "fixture", "--seasons", "2015-2016"]) == 1
    assert main(["--source", "nope"]) == 2
