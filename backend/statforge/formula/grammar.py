"""Week 1 language specification for user-defined NFL statistics.

This module defines the supported *language*, not an evaluator. The restricted
AST parser and evaluator are scheduled for Week 3. The API and frontend should
use the same field allowlist so source-specific/identity columns cannot be
referenced as numeric inputs.
"""

from dataclasses import dataclass
from typing import Final

from statforge.ingest.fields import STAT_FIELDS, STAT_FIELD_NAMES

MAX_FORMULA_LENGTH: Final[int] = 256
MAX_AST_DEPTH: Final[int] = 20
MAX_ABS_CONSTANT: Final[int] = 1_000_000_000

# Names shown to users are the names used by the importer and eventual API.
ALLOWED_FIELDS: Final[frozenset[str]] = frozenset(STAT_FIELD_NAMES)

# AST mapping to be consumed by the restricted parser in Week 3.
ALLOWED_BINARY_OPERATORS: Final[frozenset[str]] = frozenset({"+", "-", "*", "/"})
ALLOWED_UNARY_OPERATORS: Final[frozenset[str]] = frozenset({"+", "-"})

# EBNF: multiplication/division bind more tightly than addition/subtraction;
# the binary operators are left-associative. Unary signs bind most tightly.
# No functions, indexing, attributes, exponentiation, or implicit multiplication.
FORMULA_EBNF: Final[str] = """\
formula        = expression ;
expression     = term , { ("+" | "-") , term } ;
term           = factor , { ("*" | "/") , factor } ;
factor         = { "+" | "-" } , primary ;
primary        = number | field | "(" , expression , ")" ;
number         = digits , [ "." , digits ] | "." , digits ;
digits         = digit , { digit } ;
digit          = "0" | "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9" ;
field          = one of ALLOWED_FIELDS (exact identifier match) ;
"""


@dataclass(frozen=True)
class FormulaExample:
    """Example shared between the formula editor and API fixture planning."""

    name: str
    expression: str
    description: str
    higher_is_better: bool = True


QB_SCORE: Final[FormulaExample] = FormulaExample(
    name="QB Score",
    expression="(pass_yards + 25 * pass_td - 40 * interceptions) / pass_attempts",
    description="Weighted passing production per pass attempt (not an official NFL stat).",
)


def formula_field_dictionary() -> list[dict[str, str]]:
    """Return serializable definitions for the ten formula-eligible numeric fields.

    Identity fields (e.g. player_name, season) are deliberately excluded.
    The importer remains the single canonical owner of definitions and units.
    """
    return [
        {
            "name": field.name,
            "label": field.label,
            "definition": field.definition,
            "unit": field.unit,
        }
        for field in STAT_FIELDS
    ]
