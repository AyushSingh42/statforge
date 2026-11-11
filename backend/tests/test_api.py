import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from statforge import __version__
from statforge.api.main import app
from statforge.config import SUPPORTED_POSITIONS, SUPPORTED_SEASONS
from statforge.formula import QB_SCORE
from statforge.ingest.fields import ALL_FIELDS
from statforge.ingest.importer import import_source
from statforge.ingest.sources import get_source

client = TestClient(app)
FIXTURES = Path(__file__).parent / "fixtures"
REQUEST = {"formula": QB_SCORE.expression, "seasons": [2020], "positions": ["QB"]}


@pytest.fixture(scope="module")
def fixture_db(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "statforge.sqlite3"
    return import_source(get_source("fixture"), SUPPORTED_SEASONS, path)


@pytest.fixture(autouse=True)
def use_fixture_db(fixture_db, monkeypatch):
    monkeypatch.setenv("STATFORGE_DB_PATH", str(fixture_db.path))


def evaluate(**overrides):
    return client.post("/evaluate", json={**REQUEST, **overrides})


def test_health_reports_version_and_source(monkeypatch):
    monkeypatch.setenv("STATFORGE_DATA_SOURCE", "fixture")
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__, "data_source": "fixture"}


def test_fields_lists_the_dictionary_in_order(fixture_db):
    body = client.get("/fields").json()
    assert body["dataset_version"] == fixture_db.dataset_version
    assert [f["name"] for f in body["fields"]] == [f.name for f in ALL_FIELDS]
    assert body["fields"][4] == {
        "name": "games",
        "label": "Games played",
        "definition": "Regular-season games with a recorded snap.",
        "unit": "games",
        "kind": "stat",
    }


def test_seasons_reports_imported_scope_and_attribution(fixture_db):
    body = client.get("/seasons").json()
    assert body["seasons"] == list(SUPPORTED_SEASONS)
    assert body["positions"] == list(SUPPORTED_POSITIONS)
    assert body["dataset"]["dataset_version"] == fixture_db.dataset_version
    assert body["dataset"]["source_attribution"].startswith("StatForge synthetic fixture")


def test_missing_database_is_a_503(monkeypatch, tmp_path):
    monkeypatch.setenv("STATFORGE_DB_PATH", str(tmp_path / "absent.sqlite3"))
    for response in (client.get("/fields"), client.get("/seasons"), evaluate()):
        assert response.status_code == 503
        assert "statforge.ingest.importer" in response.json()["detail"]


def test_evaluate_matches_the_agreed_response_fixture(fixture_db):
    response = evaluate(minimums={"pass_attempts": 200})
    assert response.status_code == 200
    body = response.json()
    assert body.pop("request_id")
    expected = json.loads((FIXTURES / "evaluate_response.json").read_text())
    expected["dataset_version"] = fixture_db.dataset_version
    assert body == expected


def test_evaluate_filters_seasons_and_positions_in_the_query():
    body = evaluate(seasons=[2016, 2017], positions=["QB", "TE"]).json()
    assert body["counts"]["selected"] == 8
    assert {(r["season"], r["position"]) for r in body["records"]} == {
        (s, p) for s in (2016, 2017) for p in ("QB", "TE")
    }


def test_unavailable_rows_are_not_request_errors():
    body = evaluate(positions=["RB"]).json()
    assert body["counts"]["available"] == 0
    assert body["unavailable_by_reason"] == {"division_by_zero": 2}


def test_bad_formula_is_a_structured_422():
    response = evaluate(formula="sqrt(games)")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "unsupported_syntax"
    assert response.json()["detail"]["request_id"]


def test_request_shape_errors_are_422():
    assert evaluate(seasons=[1900]).status_code == 422
    assert evaluate(minimums={"pass_attempts": "200"}).status_code == 422


def test_thresholds_are_inclusive_and_combined_with_and():
    body = evaluate(minimums={"games": 16, "pass_attempts": 400}).json()
    assert len(body["records"]) == 1
    assert body["counts"]["threshold_excluded"] == 1
    assert body["excluded_by_threshold"] == {"games": 1, "pass_attempts": 1}


def test_zero_threshold_keeps_zero_counts_but_not_missing_ones():
    body = evaluate(positions=["WR"], formula="rec_yards", minimums={"targets": 0}).json()
    assert len(body["records"]) == 1
    assert body["excluded_by_threshold"] == {"targets": 1}

    qbs = evaluate(formula="pass_yards", minimums={"targets": 0}).json()
    assert len(qbs["records"]) == 2  # fixture QBs have 0 targets, which meets >= 0


def test_no_matching_rows_is_an_empty_success():
    body = evaluate(minimums={"games": 1000}).json()
    assert body["records"] == []
    assert body["counts"]["threshold_excluded"] == 2
