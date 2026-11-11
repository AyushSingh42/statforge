"""StatForge HTTP API, serving the imported SQLite snapshot.

uvicorn statforge.api.main:app --reload

POST /evaluate returns unranked calculations (stage "calculation_only", see
Docs/evaluate-contract.md); ranking, ties and charts extend it in later weeks.
"""

import sqlite3
from collections import Counter
from collections.abc import Iterator
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from statforge import __version__
from statforge.api.evaluate_contract import EvaluateRequest
from statforge.config import SUPPORTED_POSITIONS, data_source_name, database_path
from statforge.db import connect
from statforge.formula import FormulaValidationError, evaluate_rows, parse_formula
from statforge.ingest.fields import IDENTITY_FIELDS

QUALIFICATION_FIELDS = ("games", "pass_attempts", "carries", "targets")

app = FastAPI(title="StatForge API", version=__version__)


class HealthResponse(BaseModel):
    status: str
    version: str
    data_source: str


class FieldDefinition(BaseModel):
    name: str
    label: str
    definition: str
    unit: str
    kind: str


class FieldsResponse(BaseModel):
    dataset_version: str
    fields: list[FieldDefinition]


class DatasetInfo(BaseModel):
    dataset_version: str
    source_name: str
    source_attribution: str
    source_url: str
    source_version: str
    imported_at: str


class SeasonsResponse(BaseModel):
    seasons: list[int]
    positions: list[str]
    dataset: DatasetInfo


def get_db() -> Iterator[sqlite3.Connection]:
    try:
        conn = connect(database_path())
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    try:
        yield conn
    finally:
        conn.close()


Db = Annotated[sqlite3.Connection, Depends(get_db)]


def _dataset(conn: sqlite3.Connection) -> DatasetInfo:
    row = conn.execute("SELECT * FROM dataset_metadata").fetchone()
    return DatasetInfo.model_validate(dict(row))


@app.get("/health")
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__, data_source=data_source_name())


@app.get("/fields")
def fields(conn: Db) -> FieldsResponse:
    rows = conn.execute(
        "SELECT name, label, definition, unit, kind FROM field_definitions ORDER BY sort_order"
    )
    return FieldsResponse(
        dataset_version=_dataset(conn).dataset_version,
        fields=[FieldDefinition.model_validate(dict(row)) for row in rows],
    )


@app.get("/seasons")
def seasons(conn: Db) -> SeasonsResponse:
    years = [r[0] for r in conn.execute("SELECT DISTINCT season FROM player_seasons ORDER BY 1")]
    present = {r[0] for r in conn.execute("SELECT DISTINCT position FROM player_seasons")}
    return SeasonsResponse(
        seasons=years,
        positions=[p for p in SUPPORTED_POSITIONS if p in present],
        dataset=_dataset(conn),
    )


def _select_rows(conn: sqlite3.Connection, request: EvaluateRequest) -> list[dict[str, object]]:
    season_marks = ", ".join("?" * len(request.seasons))
    position_marks = ", ".join("?" * len(request.positions))
    rows = conn.execute(
        "SELECT s.*, p.player_name FROM player_seasons AS s JOIN players AS p USING (player_id) "
        f"WHERE s.season IN ({season_marks}) AND s.position IN ({position_marks}) "
        "ORDER BY s.season, s.player_id",
        (*request.seasons, *request.positions),
    )
    return [dict(row) for row in rows]


@app.post("/evaluate")
def evaluate(request: EvaluateRequest, conn: Db) -> dict[str, object]:
    """Apply every requested filter, then calculate each qualifying player-season."""
    request_id = str(uuid4())
    try:
        parsed = parse_formula(request.formula)
    except FormulaValidationError as exc:
        raise HTTPException(
            status_code=422, detail={"request_id": request_id, **exc.to_dict()}
        ) from None

    selected = _select_rows(conn, request)
    # Thresholds are inclusive and combined with AND; a missing count never qualifies.
    active = request.minimums.active()
    excluded_by_threshold = dict.fromkeys(active, 0)
    qualified = []
    for row in selected:
        failed = [
            name for name, minimum in active.items() if row[name] is None or row[name] < minimum
        ]
        for name in failed:
            excluded_by_threshold[name] += 1
        if not failed:
            qualified.append(row)

    results = evaluate_rows(parsed, qualified)
    unavailable = Counter(result.reason for result in results if not result.available)
    return {
        "stage": "calculation_only",
        "request_id": request_id,
        "dataset_version": _dataset(conn).dataset_version,
        "formula": parsed.expression,
        "required_fields": list(parsed.fields),
        "applied_filters": request.model_dump(exclude={"formula", "higher_is_better"}),
        "higher_is_better": request.higher_is_better,
        "counts": {
            "selected": len(selected),
            "threshold_excluded": len(selected) - len(qualified),
            "evaluated": len(results),
            "available": sum(result.available for result in results),
            "unavailable": sum(unavailable.values()),
        },
        "excluded_by_threshold": excluded_by_threshold,
        "unavailable_by_reason": dict(unavailable),
        "records": [
            {
                **{field.name: row[field.name] for field in IDENTITY_FIELDS},
                "qualification_counts": {name: row[name] for name in QUALIFICATION_FIELDS},
                "result": result.to_dict(),
            }
            for row, result in zip(qualified, results, strict=True)
        ],
    }
