"""Week 1 contract tests: grammar vocabulary and public field metadata."""

from statforge.formula.grammar import (
    ALLOWED_BINARY_OPERATORS,
    ALLOWED_FIELDS,
    ALLOWED_UNARY_OPERATORS,
    FORMULA_EBNF,
    MAX_ABS_CONSTANT,
    MAX_AST_DEPTH,
    MAX_FORMULA_LENGTH,
    QB_SCORE,
    formula_field_dictionary,
)
from statforge.ingest.fields import IDENTITY_FIELDS, STAT_FIELDS, STAT_FIELD_NAMES


def test_allowed_fields_share_importer_canonical_names():
    assert ALLOWED_FIELDS == frozenset(STAT_FIELD_NAMES)
    assert len(ALLOWED_FIELDS) == 10
    assert not ALLOWED_FIELDS.intersection({field.name for field in IDENTITY_FIELDS})


def test_each_formula_field_has_unique_name_definition_and_unit():
    definitions = formula_field_dictionary()
    assert len(definitions) == len(STAT_FIELDS)
    assert len({field["name"] for field in definitions}) == len(definitions)
    assert {field["name"] for field in definitions} == ALLOWED_FIELDS
    for field in definitions:
        assert all(field[key].strip() for key in ("name", "label", "definition", "unit"))
        assert set(field) == {"name", "label", "definition", "unit"}


def test_field_dictionary_is_json_serializable():
    import json

    assert json.loads(json.dumps(formula_field_dictionary())) == formula_field_dictionary()


def test_supported_operators_and_limits_are_explicit():
    assert ALLOWED_BINARY_OPERATORS == {"+", "-", "*", "/"}
    assert ALLOWED_UNARY_OPERATORS == {"+", "-"}
    assert 0 < MAX_FORMULA_LENGTH <= 1024
    assert 0 < MAX_AST_DEPTH <= 64
    assert 0 < MAX_ABS_CONSTANT < 10**15
    assert "expression" in FORMULA_EBNF and "primary" in FORMULA_EBNF
    assert "field" in FORMULA_EBNF and "number" in FORMULA_EBNF


def test_worked_example_uses_supported_names_and_has_known_answer():
    assert QB_SCORE.expression == (
        "(pass_yards + 25 * pass_td - 40 * interceptions) / pass_attempts"
    )
    assert {"pass_yards", "pass_td", "interceptions", "pass_attempts"} <= ALLOWED_FIELDS
    assert (3000 + 25 * 20 - 40 * 10) / 400 == 7.75
