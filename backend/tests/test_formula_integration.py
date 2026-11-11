"""Engine handoff to the existing importer, sqlite3 rows and a real HTTP adapter."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from statforge.api.formula_demo import app
from statforge.formula import QB_SCORE, evaluate_formula, evaluate_rows
from statforge.ingest.normalize import normalize_row
from statforge.ingest.sources import get_source

client = TestClient(app)
REQUEST = {"formula": QB_SCORE.expression, "seasons": [2020], "positions": ["QB"]}


def test_existing_csv_normalizer_and_engine_agree():
    source = get_source("fixture")
    rows = [normalize_row(raw, source.column_map) for raw in source.fetch([2020])]
    results = evaluate_rows(QB_SCORE.expression, rows)
    assert len(results) == 8
    assert results[0].value == 7.75
    assert results[1].value == pytest.approx(20 / 3)
    assert [result.reason for result in results[2:]] == ["division_by_zero"] * 6


def test_sqlite_row_adapter():
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT ? AS pass_yards, ? AS pass_td, ? AS interceptions, ? AS pass_attempts",
            (3000, 20, 10, 400),
        ).fetchone()
        assert evaluate_formula(QB_SCORE.expression, dict(row)).value == 7.75


def test_http_success_matches_reviewable_response_fixture():
    request = {**REQUEST, "minimums": {"pass_attempts": 200}}
    response = client.post("/evaluate", json=request)
    assert response.status_code == 200
    body = response.json()
    assert body.pop("request_id")
    path = Path(__file__).parent / "fixtures" / "evaluate_response.json"
    expected = json.loads(path.read_text())
    assert body == expected
    assert body["records"][0]["result"]["value"] == 7.75


def test_http_unavailable_rows_are_not_request_errors():
    response = client.post("/evaluate", json={**REQUEST, "positions": ["RB"]})
    assert response.status_code == 200
    body = response.json()
    assert body["counts"]["available"] == 0
    assert body["unavailable_by_reason"] == {"division_by_zero": 2}
    assert all(record["result"]["value"] is None for record in body["records"])


def test_http_bad_formula_has_structured_error_even_when_filters_match_no_rows():
    response = client.post(
        "/evaluate",
        json={**REQUEST, "formula": "sqrt(games)", "minimums": {"games": 1000}},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "unsupported_syntax"
    assert response.json()["detail"]["request_id"]


def test_http_empty_success_and_request_validation():
    response = client.post("/evaluate", json={**REQUEST, "minimums": {"games": 1000}})
    assert response.status_code == 200
    assert response.json()["records"] == []
    assert response.json()["counts"]["threshold_excluded"] == 2
    assert client.post("/evaluate", json={**REQUEST, "seasons": [1900]}).status_code == 422


def test_all_thresholds_are_inclusive_and_combined_with_and():
    body = client.post(
        "/evaluate", json={**REQUEST, "minimums": {"games": 16, "pass_attempts": 400}}
    ).json()
    assert len(body["records"]) == 1
    assert body["counts"]["threshold_excluded"] == 1
    assert body["excluded_by_threshold"] == {"games": 1, "pass_attempts": 1}


def test_missing_threshold_value_fails_even_for_zero_threshold():
    body = client.post(
        "/evaluate",
        json={
            **REQUEST,
            "positions": ["WR"],
            "formula": "rec_yards",
            "minimums": {"targets": 0},
        },
    ).json()
    assert len(body["records"]) == 1
    assert body["excluded_by_threshold"] == {"targets": 1}


def test_changing_rank_direction_is_metadata_only_until_ranking_exists():
    request = {**REQUEST, "higher_is_better": False}
    body = client.post("/evaluate", json=request).json()
    assert body["stage"] == "calculation_only"
    assert body["higher_is_better"] is False
    assert [record["player_id"] for record in body["records"]] == ["FX-QB-01", "FX-QB-02"]
