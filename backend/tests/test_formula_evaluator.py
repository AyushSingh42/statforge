"""Numerical behavior, unavailable results, batching and independent fixtures."""

import json
import math
from decimal import Decimal
from pathlib import Path

import pytest

from statforge.formula import (
    QB_SCORE,
    FormulaValidationError,
    evaluate_formula,
    evaluate_rows,
    parse_formula,
)

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "formula_cases.json").read_text())


@pytest.mark.parametrize("case", FIXTURES, ids=lambda case: case["name"])
def test_hand_computed_fixtures(case):
    result = evaluate_formula(case["formula"], case["stats"])
    assert result.to_dict() == case["expected"]
    json.dumps(result.to_dict(), allow_nan=False)


@pytest.mark.parametrize("raw", ["400", True, False, [], {}, complex(1, 0), Decimal("400")])
def test_non_native_numbers_are_unavailable_not_coerced(raw):
    result = evaluate_formula("pass_attempts", {"pass_attempts": raw})
    assert not result.available
    assert result.reason == "invalid_value"
    assert result.field == "pass_attempts"


@pytest.mark.parametrize("raw", [math.nan, math.inf, -math.inf, 10**400])
def test_non_finite_or_unrepresentable_inputs_are_unavailable(raw):
    result = evaluate_formula("pass_yards", {"pass_yards": raw})
    assert result.reason == "non_finite_input"
    assert result.value is None
    json.dumps(result.to_dict(), allow_nan=False)


@pytest.mark.parametrize("stats", [{}, {"games": None}])
def test_missing_inputs_remain_missing_even_when_multiplied_by_zero(stats):
    result = evaluate_formula("0 * games", stats)
    assert result.reason == "missing_value"
    assert result.field == "games"


def test_unused_missing_or_invalid_stats_do_not_exclude_a_row():
    result = evaluate_formula("pass_yards", {"pass_yards": 0, "targets": None, "games": "bad"})
    assert result.available
    assert result.value == 0


def test_missing_fields_are_reported_deterministically():
    result = evaluate_formula("pass_yards + games", {})
    assert result.field == "games"


@pytest.mark.parametrize("denominator", [0, 0.0, -0.0])
def test_zero_denominator_is_unavailable(denominator):
    result = evaluate_formula("1 / pass_attempts", {"pass_attempts": denominator})
    assert result.reason == "division_by_zero"


def test_expression_denominator_and_constant_zero():
    assert evaluate_formula("games / (games - games)", {"games": 16}).reason == "division_by_zero"
    assert evaluate_formula("1 / 0", {}).reason == "division_by_zero"
    assert evaluate_formula("0 / games", {"games": 16}).value == 0


@pytest.mark.parametrize(
    "formula, stats",
    [
        ("pass_yards * pass_yards", {"pass_yards": 1e308}),
        ("pass_yards + pass_yards", {"pass_yards": 1e308}),
        ("pass_yards - rush_yards", {"pass_yards": 1e308, "rush_yards": -1e308}),
        ("pass_yards / pass_attempts", {"pass_yards": 1e308, "pass_attempts": 1e-308}),
        ("(pass_yards * pass_yards) / pass_yards", {"pass_yards": 1e308}),
    ],
)
def test_non_finite_intermediates_are_rejected(formula, stats):
    result = evaluate_formula(formula, stats)
    assert result.reason == "non_finite_result"
    assert not result.available
    json.dumps(result.to_dict(), allow_nan=False)


def test_no_display_rounding_or_small_denominator_cutoff():
    assert evaluate_formula("1 / 3", {}).value == 1 / 3
    assert evaluate_formula("1 / games", {"games": 1e-12}).value == 1e12


def test_aggregated_counts_are_used_not_mean_of_per_team_rates():
    # Team A: 100/10 = 10; team B: 900/30 = 30. Total: 1000/40 = 25, not 20.
    result = evaluate_formula(
        "pass_yards / pass_attempts", {"pass_yards": 1000, "pass_attempts": 40}
    )
    assert result.value == 25


def test_batch_parses_once_preserves_order_and_does_not_mutate_rows(monkeypatch):
    import statforge.formula.evaluator as evaluator

    original_parse = evaluator.parse_formula
    calls = []

    def tracked_parse(expression):
        calls.append(expression)
        return original_parse(expression)

    monkeypatch.setattr(evaluator, "parse_formula", tracked_parse)
    rows = [{"games": 4}, {"games": None}, {"games": 0}, {"games": 2}]
    before = [dict(row) for row in rows]
    results = evaluate_rows("8 / games", iter(rows))
    assert [result.value for result in results] == [2.0, None, None, 4.0]
    assert [result.reason for result in results] == [
        None,
        "missing_value",
        "division_by_zero",
        None,
    ]
    assert calls == ["8 / games"]
    assert rows == before
    assert evaluate_rows(original_parse("1"), [{}])[0].value == 1


def test_invalid_formulas_fail_even_for_empty_batches():
    with pytest.raises(FormulaValidationError):
        evaluate_rows("not_a_field", [])
    assert evaluate_rows("games", []) == []


def test_preparsed_plan_does_not_need_ast_at_runtime(monkeypatch):
    parsed = parse_formula(QB_SCORE.expression)

    def forbidden(*args, **kwargs):
        raise AssertionError("Runtime attempted Python parsing or evaluation")

    monkeypatch.setattr("statforge.formula.parser.ast.parse", forbidden)
    monkeypatch.setattr("builtins.eval", forbidden)
    result = evaluate_formula(
        parsed, {"pass_yards": 3000, "pass_td": 20, "interceptions": 10, "pass_attempts": 400}
    )
    assert result.value == 7.75


@pytest.mark.parametrize("bad", [None, 5, True, []])
def test_invalid_internal_argument_types_fail_clearly(bad):
    with pytest.raises(TypeError):
        evaluate_formula(bad, {})
    with pytest.raises(TypeError):
        evaluate_rows(bad, [])
    with pytest.raises(TypeError, match="mapping"):
        evaluate_formula("1", bad)
