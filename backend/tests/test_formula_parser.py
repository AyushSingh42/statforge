"""Public language tests, including hostile syntax and exact limit boundaries."""

from dataclasses import FrozenInstanceError

import pytest

from statforge.formula import (
    ALLOWED_FIELDS,
    MAX_AST_DEPTH,
    MAX_FORMULA_LENGTH,
    FormulaValidationError,
    evaluate_formula,
    parse_formula,
)


@pytest.mark.parametrize(
    "expression, expected",
    [
        ("2 + 3 * 4", 14),
        ("(2 + 3) * 4", 20),
        ("20 / 5 / 2", 2),
        ("10 - 3 - 2", 5),
        ("-2 * 3", -6),
        ("-(2 + 3)", -5),
        ("--2", 2),
        ("+-+2", -2),
        ("+2", 2),
        (".5 + 1.25", 1.75),
        ("0012 + 000.5", 12.5),
        ("\t 1\n+\r2 \f+\v3 ", 6),
        ("0", 0),
        ("-1000000000", -1_000_000_000),
        ("1000000000.000", 1_000_000_000),
    ],
)
def test_precedence_associativity_and_number_grammar(expression, expected):
    parsed = parse_formula(expression)
    assert parsed.expression == expression
    assert parsed.fields == ()
    assert evaluate_formula(parsed, {}).value == expected


@pytest.mark.parametrize("name", sorted(ALLOWED_FIELDS))
def test_all_canonical_statistics_are_accepted(name):
    assert parse_formula(name).fields == (name,)


def test_required_fields_are_sorted_deduplicated_and_plan_is_immutable():
    parsed = parse_formula("pass_yards + pass_yards / games")
    assert parsed.fields == ("games", "pass_yards")
    with pytest.raises(FrozenInstanceError):
        parsed.expression = "different"
    with pytest.raises(FrozenInstanceError):
        parsed._instructions[0].operation = "divide"


@pytest.mark.parametrize("expression", [None, 4, True, {}, []])
def test_non_string_formulas_have_a_readable_error(expression):
    with pytest.raises(FormulaValidationError) as exc:
        parse_formula(expression)
    assert exc.value.code == "invalid_formula_type"


@pytest.mark.parametrize("expression", ["", " ", "\t\r\n"])
def test_empty_formula(expression):
    with pytest.raises(FormulaValidationError) as exc:
        parse_formula(expression)
    assert exc.value.code == "empty_formula"


@pytest.mark.parametrize(
    "expression, code",
    [
        ("player_id", "unknown_field"),
        ("player_name", "unknown_field"),
        ("season", "unknown_field"),
        ("position", "unknown_field"),
        ("passing_yards", "unknown_field"),
        ("PASS_YARDS", "unknown_field"),
        ("unknown", "unknown_field"),
        ("1e3", "invalid_number"),
        ("1E-3", "invalid_number"),
        ("0x10", "invalid_number"),
        ("0b11", "invalid_number"),
        ("0o17", "invalid_number"),
        ("1_000", "invalid_number"),
        ("2j", "invalid_number"),
        ("1.", "invalid_number"),
        ("1.2.3", "invalid_number"),
        ("1000000001", "constant_too_large"),
        ("-1000000001", "constant_too_large"),
        ("1000000000.0000000001", "constant_too_large"),
        ("9" * 200, "constant_too_large"),
        ("1 +", "invalid_syntax"),
        ("1 2", "invalid_syntax"),
        ("1 .5", "invalid_syntax"),
        ("(1", "invalid_syntax"),
        ("1)", "invalid_syntax"),
        ("()", "unsupported_syntax"),
        ("2 ** 3", "unsupported_operator"),
        ("2 // 3", "unsupported_operator"),
        ("games and targets", "unsupported_syntax"),
        ("games if games else 0", "unsupported_syntax"),
        ("not games", "unsupported_syntax"),
        ("True", "unsupported_syntax"),
        ("False", "unsupported_syntax"),
        ("None", "unsupported_syntax"),
        ("abs(games)", "unsupported_syntax"),
        ("games()", "unsupported_syntax"),
        ("2(games)", "unsupported_syntax"),
        ("games.__class__", "unsupported_syntax"),
        ("games[0]", "unsupported_syntax"),
        ("[games]", "unsupported_syntax"),
        ("{games}", "unsupported_syntax"),
        ("(games, targets)", "unsupported_syntax"),
        ("lambda: 1", "unsupported_syntax"),
        ("(games := 1)", "unsupported_syntax"),
        ("'1'", "unsupported_syntax"),
        ('__import__("os").system("echo BAD")', "unsupported_syntax"),
        ("1 # ignored", "unsupported_syntax"),
        ("1 \\\n+ 2", "unsupported_syntax"),
        ("1 % 2", "unsupported_syntax"),
        ("1 == 1", "unsupported_syntax"),
        ("1 << 2", "unsupported_syntax"),
        ("1 | 2", "unsupported_syntax"),
        ("1 @ 2", "unsupported_syntax"),
        ("1; 2", "unsupported_syntax"),
        ("1\x00", "unsupported_syntax"),
        ("ｇａｍｅｓ", "unsupported_syntax"),
        ("1 × 2", "unsupported_syntax"),
        ("1\u00a0+2", "unsupported_syntax"),
    ],
)
def test_rejects_out_of_language_input(expression, code):
    with pytest.raises(FormulaValidationError) as exc:
        parse_formula(expression)
    assert exc.value.code == code
    assert str(exc.value) == exc.value.message
    assert exc.value.to_dict() == {
        "code": code,
        "message": exc.value.message,
        "column": exc.value.column,
    }
    assert exc.value.column is None or 1 <= exc.value.column <= len(expression)


def test_error_position_refers_to_original_text_even_after_normalizing_tokens():
    with pytest.raises(FormulaValidationError) as exc:
        parse_formula("  0001 + unknown")
    assert exc.value.column == 10


def test_length_includes_whitespace_and_is_checked_before_ast(monkeypatch):
    assert evaluate_formula("1" + " " * (MAX_FORMULA_LENGTH - 1), {}).value == 1

    def should_not_parse(*args, **kwargs):
        raise AssertionError("Oversized input reached ast.parse")

    monkeypatch.setattr("statforge.formula.parser.ast.parse", should_not_parse)
    with pytest.raises(FormulaValidationError) as exc:
        parse_formula("1" + " " * MAX_FORMULA_LENGTH)
    assert exc.value.code == "formula_too_long"


def test_parentheses_depth_boundary():
    assert evaluate_formula("(" * MAX_AST_DEPTH + "1" + ")" * MAX_AST_DEPTH, {}).value == 1
    with pytest.raises(FormulaValidationError) as exc:
        parse_formula("(" * (MAX_AST_DEPTH + 1) + "1" + ")" * (MAX_AST_DEPTH + 1))
    assert exc.value.code == "formula_too_deep"


@pytest.mark.parametrize("build", [lambda n: "+" * (n - 1) + "1", lambda n: "+".join(["1"] * n)])
def test_expression_depth_boundary(build):
    parse_formula(build(MAX_AST_DEPTH))
    with pytest.raises(FormulaValidationError) as exc:
        parse_formula(build(MAX_AST_DEPTH + 1))
    assert exc.value.code == "formula_too_deep"


def test_generated_arithmetic_matches_an_independent_fraction_oracle():
    import random
    from fractions import Fraction

    rng = random.Random(222)

    def make_expression(depth):
        if not depth or rng.randrange(4) == 0:
            number = rng.randint(1, 9)
            return str(number), Fraction(number)
        left, a = make_expression(depth - 1)
        right, b = make_expression(depth - 1)
        op = rng.choice("+-*/")
        if op == "/" and not b:
            op = "+"
        if op == "+":
            expected = a + b
        elif op == "-":
            expected = a - b
        elif op == "*":
            expected = a * b
        else:
            expected = a / b
        return f"({left} {op} {right})", expected

    for _ in range(300):
        expression, expected = make_expression(3)
        assert evaluate_formula(expression, {}).value == pytest.approx(float(expected))


def test_short_arbitrary_strings_cannot_escape_validation():
    import random

    rng = random.Random(222)
    alphabet = "abcdef0123456789+-*/()._ \n\t"
    for _ in range(1000):
        text = "".join(rng.choices(alphabet, k=rng.randrange(1, 100)))
        try:
            parsed = parse_formula(text)
        except FormulaValidationError:
            continue
        result = evaluate_formula(parsed, {})
        assert result.available or result.reason == "division_by_zero"
