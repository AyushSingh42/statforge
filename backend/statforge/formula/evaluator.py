"""Pure player-season calculation; no database, HTTP, sorting or display rounding."""

import math
import operator
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal, cast

from statforge.formula.parser import ParsedFormula, parse_formula

UnavailableReason = Literal[
    "missing_value", "invalid_value", "non_finite_input", "division_by_zero", "non_finite_result"
]
_BINARY = {
    "add": operator.add,
    "subtract": operator.sub,
    "multiply": operator.mul,
    "divide": operator.truediv,
}


@dataclass(frozen=True)
class EvaluationResult:
    """One value or one deterministic exclusion reason, ready for JSON serialization."""

    value: float | None
    reason: UnavailableReason | None = None
    message: str | None = None
    field: str | None = None

    @property
    def available(self) -> bool:
        return self.value is not None and self.reason is None

    def to_dict(self) -> dict[str, float | bool | str | None]:
        return {
            "value": self.value,
            "available": self.available,
            "reason": self.reason,
            "message": self.message,
            "field": self.field,
        }


def _evaluate(parsed: ParsedFormula, stats: Mapping[str, object]) -> EvaluationResult:
    if not isinstance(stats, Mapping):
        raise TypeError("stats must be a mapping of canonical fields; use dict(sqlite_row).")
    values: dict[str, float] = {}
    # Precheck every referenced field, including ones multiplied by zero. Missing
    # data cannot become a valid zero through algebraic simplification.
    for name in parsed.fields:
        raw = stats.get(name)
        if raw is None:
            return EvaluationResult(
                None, "missing_value", f"No value is available for '{name}'.", name
            )
        if type(raw) not in (int, float):
            return EvaluationResult(
                None, "invalid_value", f"'{name}' must be a number, not a string or boolean.", name
            )
        try:
            number = float(raw)
        except OverflowError:
            number = math.inf
        if not math.isfinite(number):
            return EvaluationResult(None, "non_finite_input", f"'{name}' must be finite.", name)
        values[name] = number

    stack: list[float] = []
    for instruction in parsed._instructions:
        operation = instruction.operation
        if operation == "number":
            stack.append(cast(float, instruction.operand))
        elif operation == "field":
            stack.append(values[cast(str, instruction.operand)])
        elif operation in ("positive", "negative"):
            value = stack.pop()
            stack.append(value if operation == "positive" else -value)
        else:
            right, left = stack.pop(), stack.pop()
            if operation == "divide" and right == 0:
                return EvaluationResult(
                    None, "division_by_zero", "A denominator evaluated to zero."
                )
            value = _BINARY[operation](left, right)
            if not math.isfinite(value):
                return EvaluationResult(
                    None,
                    "non_finite_result",
                    "An arithmetic operation produced a non-finite result.",
                )
            stack.append(value)
    return EvaluationResult(stack[0])


def evaluate_formula(formula: str | ParsedFormula, stats: Mapping[str, object]) -> EvaluationResult:
    """Evaluate one normalized row. Invalid formulas raise FormulaValidationError.

    Missing, non-numeric or non-finite row inputs and undefined arithmetic return
    an unavailable result instead of aborting the request. Extra fields are ignored.
    """
    parsed = parse_formula(formula) if isinstance(formula, str) else formula
    if not isinstance(parsed, ParsedFormula):
        raise TypeError("formula must be a string or the result of parse_formula().")
    return _evaluate(parsed, stats)


def evaluate_rows(
    formula: str | ParsedFormula, rows: Iterable[Mapping[str, object]]
) -> list[EvaluationResult]:
    """Parse once and return one result per input row, in the original order.

    This deliberately does not filter, aggregate, rank or mutate records. The API
    must apply requested filters; pass season totals, not averages of ratios.
    An invalid formula is rejected even when `rows` is empty.
    """
    parsed = parse_formula(formula) if isinstance(formula, str) else formula
    if not isinstance(parsed, ParsedFormula):
        raise TypeError("formula must be a string or the result of parse_formula().")
    return [_evaluate(parsed, row) for row in rows]
