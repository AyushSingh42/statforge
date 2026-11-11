# Ayush Part 2 — formula engine and API handoff

Built against `main` commit `1b310a63517d91f239ad3d543f3dd1d73f98b935`.
The request model and per-row results below are implemented, not placeholders.
The production app (`statforge.api.main`) and ingestion modules are unchanged.

## 1. Jo's integration boundary

```python
from statforge.formula import (
    FormulaValidationError,
    evaluate_formula,
    evaluate_rows,
    parse_formula,
)

parsed = parse_formula(
    "(pass_yards + 25 * pass_td - 40 * interceptions) / pass_attempts"
)

# Use existing normalize_row() output, or dict(sqlite_row) from a canonical DB.
row = {"pass_yards": 3000, "pass_td": 20, "interceptions": 10, "pass_attempts": 400}
result = evaluate_formula(parsed, row)
assert result.value == 7.75
print(result.to_dict())

# Or evaluate an iterable of already-selected, normalized rows in one call:
results = evaluate_rows(parsed, [row])
```

`parse_formula(text) -> ParsedFormula` validates once. `parsed.expression`
preserves the submitted text; `parsed.fields` is a sorted, duplicate-free tuple
of canonical statistic names. The arithmetic plan is immutable and reusable.
Do not construct `ParsedFormula` yourself or depend on its private instructions.

`evaluate_formula(text_or_parsed, stats) -> EvaluationResult` handles one row.
`evaluate_rows(text_or_parsed, rows) -> list[EvaluationResult]` parses once and
returns one result for each input row, in the same order, without mutating rows.
It also validates a formula when there are no rows.

The core engine uses only Python's standard library. It does not import FastAPI,
Pydantic or SQLite, and does not download data. The optional API contract and
HTTP example use dependencies that already exist in the backend.

### Division of responsibility

**Ayush:** formula syntax, arithmetic, required-field discovery, formula errors,
per-record unavailable reasons and tests.

**Jo:** receive `EvaluateRequest`, validate the formula before querying, select
seasons/positions, apply every active threshold, normalize/reconcile player-season
totals, call the engine, and wrap results with dataset/request metadata. Use bound
SQL parameters for values and an explicit canonical allowlist for column names.
`parsed.fields` contains only validated canonical statistic names.

The engine intentionally does **not** select seasons, apply thresholds, aggregate
traded-player records, round, sort, rank, calculate percentiles or build charts.
Jo must not accept filters and silently ignore them. The runnable example below
shows inclusive AND filtering and exclusion counts; database filtering can replace
that selection step without changing the engine interface.

## 2. Request JSON

Import `EvaluateRequest` from `statforge.api.evaluate_contract`. The ready-to-use
request fixture is `backend/tests/fixtures/evaluate_request.json`:

```json
{
  "formula": "(pass_yards + 25 * pass_td - 40 * interceptions) / pass_attempts",
  "seasons": [2020],
  "positions": ["QB"],
  "minimums": {"pass_attempts": 200},
  "higher_is_better": true
}
```

`seasons` is a required nonempty, duplicate-free list drawn from the existing
supported seasons (2016–2025). `positions` defaults to all supported positions;
when supplied it must be nonempty, duplicate-free and use `QB`, `RB`, `WR`, `TE`.
No case normalization occurs in this request model.

`minimums` accepts only `games`, `pass_attempts`, `carries` and `targets`, each a
nonnegative integer or null. Omitted/null means disabled; **zero is active**.
Every active threshold is inclusive (`>=`), and all must pass. A missing count
fails an active threshold, including zero. `request.minimums.active()` returns
only active canonical field/threshold pairs for Jo's query construction.

Unknown keys, client-supplied statistics, stringified numbers and booleans in
integer fields are rejected. `higher_is_better` is a strict boolean, default true.
It is consumed by the later ranking stage, not by arithmetic.

## 3. Result JSON: success versus unavailable

Every `EvaluationResult.to_dict()` has exactly these five keys:

```json
{"value": 7.75, "available": true, "reason": null, "message": null, "field": null}
```

A valid formula with a zero denominator is a per-row unavailable result, not a
request error and not an infinite or zero score:

```json
{
  "value": null,
  "available": false,
  "reason": "division_by_zero",
  "message": "A denominator evaluated to zero.",
  "field": null
}
```

| `reason` | Meaning |
|---|---|
| `missing_value` | A referenced field is absent or `None`. |
| `invalid_value` | A referenced value is not a native Python int/float; strings and booleans are not coerced. |
| `non_finite_input` | A referenced value is NaN/infinite, or too large to convert to a finite float. |
| `division_by_zero` | A denominator expression evaluates to zero, including negative zero. |
| `non_finite_result` | An intermediate arithmetic result becomes non-finite. |

`field` identifies the problematic input for the first three reasons, otherwise
it is null. Required inputs are checked in alphabetical order before arithmetic,
so a row with multiple input problems has one deterministic first reason. Unused
fields do not affect availability. `0 * missing_field` still remains unavailable.

Values use floating-point arithmetic, without display rounding. Binary floating
point has finite precision; results are not claims of arbitrary-precision decimal
arithmetic. Numeric **constants** have the grammar's 1e9 cap, but there is no 1e9
cap on finite input statistics or results. No epsilon is used for zero detection.
Aggregate season counts before evaluating ratios; do not average per-team rates.

## 4. Formula errors: reject the request

Catch only `FormulaValidationError` for user formula mistakes:

```python
from fastapi import HTTPException

try:
    parsed = parse_formula(request.formula)
except FormulaValidationError as exc:
    raise HTTPException(status_code=422, detail=exc.to_dict()) from None
```

`to_dict()` returns `code`, `message` and `column`. `column` is a 1-based character
position in the original submitted string, or null for a formula-wide error.
For multiline strings this is an absolute character position, not a line-local
column. Stable error codes are:

`invalid_formula_type`, `empty_formula`, `formula_too_long`, `invalid_number`,
`constant_too_large`, `invalid_syntax`, `unsupported_syntax`,
`unsupported_operator`, `unknown_field`, `formula_too_deep`.

A shape error in `EvaluateRequest` uses FastAPI/Pydantic's ordinary HTTP 422
validation-error list. A syntactically invalid formula uses the structured
formula-error detail above. The reference HTTP adapter also includes a request ID
in formula-error details. Do not catch programming errors as empty leaderboards.

## 5. Grammar and safety behavior

The Week 1 vocabulary is unchanged. Only numeric constants, the ten canonical
statistic names, parentheses, unary `+ -` and binary `+ - * /` are accepted.
Names are case-sensitive. ASCII whitespace is permitted between tokens. Integer
leading zeroes are decimal; `.5` is valid; `1.` is not in the original grammar.
Scientific notation, hexadecimal/binary/octal literals, numeric underscores,
strings, booleans, function calls, attributes, subscripts, collections, assignment,
comments, explicit backslash continuation, comparisons and exponentiation are
rejected. Unicode operator glyphs are not accepted; the editor should insert
ASCII `-`, `*` and `/` tokens.

Limits are enforced before evaluation: 256 raw characters (including whitespace),
20 nested parentheses, 20 expression levels, and numeric literal magnitude at
most 1,000,000,000. Expression depth starts at 1 for the root expression, excluding
Python's `ast.Expression` wrapper. Unary and binary expressions add a level.
A lexical pass enforces the narrower numeric grammar; an explicit AST allowlist
then translates the parsed tree into immutable arithmetic instructions. No Python
code object is executed and neither `eval` nor `exec` is called.

## 6. Runnable HTTP example — no production-route collision

From `backend/`, with the development environment installed:

```bash
python -m uvicorn statforge.api.formula_demo:app --reload --port 8001
```

In another terminal, also from `backend/`:

```bash
curl -sS http://127.0.0.1:8001/evaluate \
  -H 'Content-Type: application/json' \
  --data-binary @tests/fixtures/evaluate_request.json
```

This **separate demo app** always uses the existing synthetic `fixture` source;
it never requests the production NFL snapshot. It applies the requested filters,
parses once, calculates rows, and returns real request/dataset metadata plus
availability/exclusion counts. The example request selects one player-season
with value **7.75**. See `tests/fixtures/evaluate_response.json` for the expected
body, excluding the dynamically generated `request_id`.

The response has `stage: "calculation_only"` and `records`, not `leaderboard`.
It does not invent ranks, chart data or statistical feedback. Higher/lower-first
is echoed as metadata, and records retain source order. The final ranked
`/evaluate` response will extend this computation stage later.

Per-threshold exclusion counts overlap: a row failing games and attempts appears
in both counts. `counts.threshold_excluded` counts that row only once. Records
with unavailable calculations remain in this diagnostic response so the API can
explain their exclusion from a future ranking.

Jo can copy the parse/calculate/error-handling flow into his production route and
replace fixture loading/filtering with the database query. **Do not mount this
demo as the production application.** The existing `/health` app is unchanged.

## 7. Verification

From the repository root with the backend environment active:

```bash
bash scripts/check-ayush-part2.sh --fix
```

`--fix` runs Ruff automatic fixes/formatting only on this contribution. The script
then checks repository-wide lint/formatting, runs the full backend test suite,
and checks formula-only branch-aware coverage against a 90% minimum. Omitting
`--fix` performs checks without automatic code edits. No sports-data download is
needed.

The tests include 12 independently specified numerical/error fixtures, grammar
and attack rejection, numeric/depth limits, missing/non-finite data, batch reuse,
300 generated calculations checked against exact fractions, 1,000 short arbitrary
inputs, the existing CSV normalizer, temporary SQLite rows, and FastAPI requests.

**Local validation for this delivery:** 224 tests passed on Python 3.13.5;
formula-engine line and branch coverage are both 100%; overall branch-aware
coverage is 97.02%. Ruff was unavailable in the build environment, so lint and
formatter execution are not claimed. Run the included script in your environment
before committing; it also verifies your installed Python/dependency combination.

Reference: Python's `ast` documentation describes the syntax-tree API; StatForge's
allowlist and arithmetic behavior are defined by this code and its tests, not by
Python's full expression language.
