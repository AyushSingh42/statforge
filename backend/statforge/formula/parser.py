"""Validate the Week 1 language and produce an immutable arithmetic plan.

Python's parser provides precedence, not permission to execute Python. A lexical
check and an explicit AST allowlist precede translation to arithmetic instructions.
No AST or Python code object is exposed or executed by the evaluator.
"""

import ast
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from statforge.formula.errors import FormulaValidationError
from statforge.formula.grammar import (
    ALLOWED_FIELDS,
    MAX_ABS_CONSTANT,
    MAX_AST_DEPTH,
    MAX_FORMULA_LENGTH,
)

Operation = Literal[
    "number",
    "field",
    "positive",
    "negative",
    "add",
    "subtract",
    "multiply",
    "divide",
]
_BINARY: dict[type[ast.operator], Operation] = {
    ast.Add: "add",
    ast.Sub: "subtract",
    ast.Mult: "multiply",
    ast.Div: "divide",
}
_UNARY: dict[type[ast.unaryop], Operation] = {ast.UAdd: "positive", ast.USub: "negative"}
_NUMBER_SUFFIX = ".0123456789_abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
_TOKEN = re.compile(
    r"(?P<space>[ \t\r\n\f\v]+)"
    r"|(?P<number>[0-9]+(?:\.[0-9]+)?|\.[0-9]+)"
    r"|(?P<name>[A-Za-z_][A-Za-z_0-9]*)"
    r"|(?P<operator>\*\*|//|[()+*/-])"
    r"|(?P<invalid>.)",
    re.DOTALL,
)


@dataclass(frozen=True)
class _Instruction:
    operation: Operation
    operand: float | str | None = None


@dataclass(frozen=True)
class ParsedFormula:
    """Reusable result of parse_formula; create it through that function only.

    `expression` preserves the submitted text. `fields` is a sorted tuple of
    required canonical fields, suitable for Jo's SELECT-column allowlist.
    """

    expression: str
    fields: tuple[str, ...]
    _instructions: tuple[_Instruction, ...] = field(repr=False)


def _lex(expression: str) -> tuple[str, list[int]]:
    """Normalize tokens for ast.parse while retaining original character offsets."""
    chunks: list[str] = []
    offsets: list[int] = []
    nesting = 0
    for match in _TOKEN.finditer(expression):
        kind = match.lastgroup
        token = match.group()
        column = match.start() + 1
        if kind == "space":
            continue
        if kind == "invalid":
            raise FormulaValidationError(
                "unsupported_syntax",
                "Use only fields, decimal numbers, parentheses and + - * /.",
                column,
            )
        if kind == "number":
            # Do not turn 1e3, 0x10, 1_000, 2j or 1. into another expression.
            end = match.end()
            if end < len(expression) and expression[end] in _NUMBER_SUFFIX:
                raise FormulaValidationError(
                    "invalid_number",
                    "Use decimal numbers such as 25 or 0.5, without exponents or suffixes.",
                    column,
                )
            # Compare the decimal spelling before float conversion can round it.
            if Decimal(token) > MAX_ABS_CONSTANT:
                raise FormulaValidationError(
                    "constant_too_large",
                    f"Numeric constants must be at most {MAX_ABS_CONSTANT} in magnitude.",
                    column,
                )
            # The EBNF permits leading zeroes; interpret them as decimal, not octal.
            whole, dot, fraction = token.partition(".")
            token = str(int(whole or "0")) + (dot + fraction if dot else "")
        if token in ("**", "//"):
            raise FormulaValidationError(
                "unsupported_operator", "Only +, -, * and / are supported.", column
            )
        if token == "(":
            nesting += 1
            if nesting > MAX_AST_DEPTH:
                raise FormulaValidationError(
                    "formula_too_deep", f"Use at most {MAX_AST_DEPTH} nested parentheses.", column
                )
        elif token == ")":
            nesting -= 1
            if nesting < 0:
                raise FormulaValidationError(
                    "invalid_syntax", "Unexpected closing parenthesis.", column
                )
        chunks.append(token)
        # Each inserted space also maps to the original token; AST start offsets
        # and syntax errors can therefore be translated even after normalization.
        offsets.extend([column] * (len(token) + 1))
    if nesting:
        raise FormulaValidationError("invalid_syntax", "A closing parenthesis is missing.")
    return " ".join(chunks), offsets


def parse_formula(expression: str) -> ParsedFormula:
    """Validate once, then reuse the returned plan across any number of rows.

    Raises FormulaValidationError for user mistakes, including unsupported
    Python syntax. Limits apply to raw input length, parentheses and expression
    depth (the root expression has depth 1; ast.Expression is not counted).
    """
    if not isinstance(expression, str):
        raise FormulaValidationError("invalid_formula_type", "The formula must be a string.")
    if len(expression) > MAX_FORMULA_LENGTH:
        raise FormulaValidationError(
            "formula_too_long", f"Use at most {MAX_FORMULA_LENGTH} characters in a formula."
        )
    if not expression.strip():
        raise FormulaValidationError("empty_formula", "Enter a formula before evaluating it.")
    source, offsets = _lex(expression)

    def column(offset: int) -> int:
        return offsets[max(0, min(offset, len(offsets) - 1))]

    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as exc:
        raise FormulaValidationError(
            "invalid_syntax",
            "Check the operators, parentheses and placement of field names.",
            column((exc.offset or 1) - 1),
        ) from None

    instructions: list[_Instruction] = []
    required: set[str] = set()

    def visit(node: ast.expr, depth: int) -> None:
        position = column(node.col_offset)
        if depth > MAX_AST_DEPTH:
            raise FormulaValidationError(
                "formula_too_deep", f"Use at most {MAX_AST_DEPTH} expression levels.", position
            )
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            instructions.append(_Instruction("number", float(node.value)))
        elif isinstance(node, ast.Name):
            if node.id not in ALLOWED_FIELDS:
                raise FormulaValidationError(
                    "unknown_field",
                    f"Unknown statistic '{node.id}'. Choose a field from the dictionary.",
                    position,
                )
            required.add(node.id)
            instructions.append(_Instruction("field", node.id))
        elif isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
            visit(node.left, depth + 1)
            visit(node.right, depth + 1)
            instructions.append(_Instruction(_BINARY[type(node.op)]))
        elif isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
            visit(node.operand, depth + 1)
            instructions.append(_Instruction(_UNARY[type(node.op)]))
        else:
            raise FormulaValidationError(
                "unsupported_syntax",
                "Only numbers, statistic fields and arithmetic are allowed; "
                "no function calls or other Python syntax.",
                position,
            )

    visit(tree.body, 1)
    return ParsedFormula(expression, tuple(sorted(required)), tuple(instructions))
