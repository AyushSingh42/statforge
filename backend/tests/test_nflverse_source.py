import csv
import hashlib
import io
import json

import pytest

from statforge.ingest.download_nflverse import download_snapshot
from statforge.ingest.normalize import normalize_row
from statforge.ingest.sources.nflverse import FILE_NAME_TEMPLATE, NflverseSource

HEADERS = [
    "player_id",
    "player_name",
    "player_display_name",
    "position",
    "season",
    "season_type",
    "games",
    "attempts",
    "passing_yards",
    "passing_tds",
    "passing_interceptions",
    "carries",
    "rushing_yards",
    "receptions",
    "targets",
    "receiving_yards",
]


def player_row(**overrides):
    row = {
        "player_id": "00-0000001",
        "player_name": "T.Player",
        "player_display_name": "Test Player",
        "position": "QB",
        "season": "2020",
        "season_type": "REG",
        "games": "16",
        "attempts": "500",
        "passing_yards": "4000",
        "passing_tds": "30",
        "passing_interceptions": "10",
        "carries": "30",
        "rushing_yards": "100",
        "receptions": "0",
        "targets": "0",
        "receiving_yards": "0",
    }
    row.update(overrides)
    return row


def write_rows(path, rows):
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def test_nflverse_source_reads_regular_season_snapshot(tmp_path):
    write_rows(
        tmp_path / FILE_NAME_TEMPLATE.format(season=2020),
        [
            player_row(),
            player_row(player_id="post", season_type="POST"),
            player_row(player_id="", player_name="Team"),
        ],
    )

    source = NflverseSource(tmp_path)
    rows = list(source.fetch([2020]))

    assert len(rows) == 1
    assert normalize_row(rows[0], source.column_map) == {
        "player_id": "00-0000001",
        "player_name": "Test Player",
        "position": "QB",
        "season": 2020,
        "games": 16,
        "pass_attempts": 500,
        "pass_yards": 4000,
        "pass_td": 30,
        "interceptions": 10,
        "carries": 30,
        "rush_yards": 100,
        "receptions": 0,
        "targets": 0,
        "rec_yards": 0,
    }


def test_nflverse_source_explains_how_to_get_a_missing_snapshot(tmp_path):
    with pytest.raises(FileNotFoundError, match="download_nflverse"):
        list(NflverseSource(tmp_path).fetch([2020]))


def test_download_snapshot_writes_csv_and_checksum(monkeypatch, tmp_path):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=HEADERS)
    writer.writeheader()
    writer.writerow(player_row())
    payload = buffer.getvalue().encode()

    monkeypatch.setattr(
        "statforge.ingest.download_nflverse.urlopen",
        lambda request, timeout: io.BytesIO(payload),
    )

    manifest = download_snapshot([2020], tmp_path)

    snapshot = tmp_path / FILE_NAME_TEMPLATE.format(season=2020)
    assert snapshot.read_bytes() == payload
    assert manifest["files"]["2020"]["sha256"] == hashlib.sha256(payload).hexdigest()
    assert json.loads((tmp_path / "manifest.json").read_text()) == manifest
