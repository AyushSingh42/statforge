import csv
import sqlite3

import pytest

from statforge.config import SUPPORTED_SEASONS
from statforge.db import SCHEMA_VERSION, connect
from statforge.formula import QB_SCORE, evaluate_formula
from statforge.ingest.fields import ALL_FIELDS, FIELD_NAMES
from statforge.ingest.importer import ImportFailedError, import_source, main, merge_stints
from statforge.ingest.sources import SOURCES, CsvSource, SourceInfo, get_source

INFO = SourceInfo(name="test", attribution="test data", url="", version="t1")


def write_source(tmp_path, rows):
    path = tmp_path / "rows.csv"
    with path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(FIELD_NAMES)
        writer.writerows(rows)
    return CsvSource(INFO, path, {name: name for name in FIELD_NAMES})


def season_rows(season, **stat_overrides):
    rows = []
    for pos in ["QB", "RB", "WR", "TE"]:
        stats = {name: "1" for name in FIELD_NAMES[4:]}
        stats.update(stat_overrides.get(pos, {}))
        rows.append([f"P{pos}", f"Player {pos}", pos, season, *stats.values()])
    return rows


@pytest.fixture
def fixture_db(tmp_path):
    path = tmp_path / "statforge.sqlite3"
    import_source(get_source("fixture"), SUPPORTED_SEASONS, path)
    return path


def test_fixture_import_populates_every_table(fixture_db):
    with connect(fixture_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM player_seasons").fetchone()[0] == 80
        assert conn.execute("SELECT COUNT(*) FROM players").fetchone()[0] == 8
        query = "SELECT name FROM field_definitions ORDER BY sort_order"
        fields = [r["name"] for r in conn.execute(query)]
        assert fields == [f.name for f in ALL_FIELDS]
        meta = dict(conn.execute("SELECT * FROM dataset_metadata").fetchone())
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert meta["source_name"] == "fixture"
    assert meta["dataset_version"].startswith("fixture-")
    assert (meta["first_season"], meta["last_season"]) == (2016, 2025)
    assert meta["player_season_count"] == 80


def test_db_rows_feed_the_formula_engine(fixture_db):
    with connect(fixture_db) as conn:
        row = conn.execute(
            "SELECT * FROM player_seasons WHERE player_id = 'FX-QB-01' AND season = 2016"
        ).fetchone()
    assert evaluate_formula(QB_SCORE.expression, dict(row)).value == 7.75


def test_missing_values_stay_null(fixture_db):
    with connect(fixture_db) as conn:
        nulls = conn.execute("SELECT COUNT(*) FROM player_seasons WHERE targets IS NULL")
        assert nulls.fetchone()[0] == len(SUPPORTED_SEASONS)


def test_reimport_replaces_rather_than_appends(fixture_db):
    with connect(fixture_db) as conn:
        first = conn.execute("SELECT dataset_version FROM dataset_metadata").fetchone()[0]
    summary = import_source(get_source("fixture"), SUPPORTED_SEASONS, fixture_db)
    with connect(fixture_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM player_seasons").fetchone()[0] == 80
    assert summary.dataset_version == first


def test_traded_player_rows_are_summed(tmp_path):
    rows = season_rows(2020) + [["PWR", "Player WR", "WR", 2020, *["2"] * 10]]
    summary = import_source(write_source(tmp_path, rows), [2020], tmp_path / "db.sqlite3")
    assert summary.merged_rows == 1
    with connect(tmp_path / "db.sqlite3") as conn:
        wr = conn.execute("SELECT * FROM player_seasons WHERE player_id = 'PWR'").fetchall()
    assert len(wr) == 1 and wr[0]["rec_yards"] == 3


def test_merge_keeps_unknown_totals_unknown():
    stint = {"player_id": "P", "season": 2020, **dict.fromkeys(FIELD_NAMES[4:], 1)}
    merged, folded = merge_stints([stint, {**stint, "targets": None}])
    assert folded == 1
    assert merged[0]["targets"] is None and merged[0]["receptions"] == 2


def test_unsupported_positions_are_not_stored(tmp_path):
    rows = season_rows(2020) + [["PK", "Kicker", "K", 2020, *["1"] * 10]]
    summary = import_source(write_source(tmp_path, rows), [2020], tmp_path / "db.sqlite3")
    assert summary.player_seasons == 4


def test_failed_import_leaves_existing_db_untouched(tmp_path, fixture_db):
    missing_te = [r for r in season_rows(2020) if r[2] != "TE"]
    with pytest.raises(ImportFailedError, match="no TE rows"):
        import_source(write_source(tmp_path, missing_te), [2020], fixture_db)
    with connect(fixture_db) as conn:
        assert conn.execute("SELECT source_name FROM dataset_metadata").fetchone()[0] == "fixture"
    assert not fixture_db.with_name(fixture_db.name + ".tmp").exists()


def test_api_connection_is_read_only(fixture_db):
    with connect(fixture_db) as conn, pytest.raises(sqlite3.OperationalError, match="readonly"):
        conn.execute("DELETE FROM player_seasons")


def test_connect_explains_missing_database(tmp_path):
    with pytest.raises(FileNotFoundError, match="statforge.ingest.importer"):
        connect(tmp_path / "absent.sqlite3")


def test_cli_exit_codes(tmp_path, capsys, monkeypatch):
    db = tmp_path / "cli.sqlite3"
    assert main(["--source", "fixture", "--db", str(db)]) == 0
    assert "Dataset version: fixture-" in capsys.readouterr().out
    assert main(["--source", "nope", "--db", str(db)]) == 2

    broken = write_source(tmp_path, season_rows(2020)[:1])
    monkeypatch.setitem(SOURCES, "broken", lambda: broken)
    assert main(["--source", "broken", "--seasons", "2020", "--db", str(db)]) == 1
    assert "was not changed" in capsys.readouterr().err
