"""Runnable, synthetic-data-only integration reference for Jo.

From backend/: uvicorn statforge.api.formula_demo:app --reload --port 8001
This is not statforge.api.main:app and is not a finished leaderboard endpoint.
Replace fixture selection with Jo's database query when integrating; keep the
engine calls and the distinction between request errors and unavailable rows.
"""

from collections import Counter
from uuid import uuid4

from fastapi import FastAPI, HTTPException

from statforge.api.evaluate_contract import EvaluateRequest
from statforge.formula import FormulaValidationError, evaluate_rows, parse_formula
from statforge.ingest.fields import IDENTITY_FIELDS
from statforge.ingest.normalize import normalize_row
from statforge.ingest.sources import get_source

app = FastAPI(title="StatForge formula integration example (synthetic data only)")


@app.post("/evaluate")
def evaluate(request: EvaluateRequest) -> dict[str, object]:
    """Return unranked calculations; every requested filter is actually applied."""
    request_id = str(uuid4())
    try:
        parsed = parse_formula(request.formula)
    except FormulaValidationError as exc:
        raise HTTPException(
            status_code=422, detail={"request_id": request_id, **exc.to_dict()}
        ) from None

    # Explicit fixture selection: never use the configured production source here.
    source = get_source("fixture")
    rows = [normalize_row(raw, source.column_map) for raw in source.fetch(request.seasons)]
    selected = [row for row in rows if row["position"] in request.positions]
    active = request.minimums.active()
    excluded_by_threshold = dict.fromkeys(active, 0)
    qualified = []
    threshold_excluded = 0
    for row in selected:
        failed = [
            name for name, minimum in active.items() if row[name] is None or row[name] < minimum
        ]
        for name in failed:
            excluded_by_threshold[name] += 1
        if failed:
            threshold_excluded += 1
        else:
            qualified.append(row)

    results = evaluate_rows(parsed, qualified)
    records = [
        {
            **{field.name: row[field.name] for field in IDENTITY_FIELDS},
            "qualification_counts": {
                name: row[name] for name in ("games", "pass_attempts", "carries", "targets")
            },
            "result": result.to_dict(),
        }
        for row, result in zip(qualified, results, strict=True)
    ]
    unavailable = Counter(result.reason for result in results if not result.available)
    return {
        "stage": "calculation_only",
        "request_id": request_id,
        "dataset_version": source.info.version,
        "formula": parsed.expression,
        "required_fields": list(parsed.fields),
        "applied_filters": request.model_dump(exclude={"formula", "higher_is_better"}),
        # Metadata only in this stage: records retain input order, not rank order.
        "higher_is_better": request.higher_is_better,
        "counts": {
            "selected": len(selected),
            "threshold_excluded": threshold_excluded,
            "evaluated": len(results),
            "available": sum(result.available for result in results),
            "unavailable": sum(unavailable.values()),
        },
        "excluded_by_threshold": excluded_by_threshold,
        "unavailable_by_reason": dict(unavailable),
        "records": records,
    }
