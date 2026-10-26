# Formula engine — Week 1 contract (Ayush)

This document fixes the **formula language and field vocabulary** before the UI,
API, and calculation engine are written. Implementation lives in
`backend/statforge/formula/grammar.py`. This is the Week 1 deliverable;
parsing, runtime validation, and evaluation belong to later weeks.

## Supported syntax

```ebnf
formula        = expression ;
expression     = term , { ("+" | "-") , term } ;
term           = factor , { ("*" | "/") , factor } ;
factor         = { "+" | "-" } , primary ;
primary        = number | field | "(" , expression , ")" ;
number         = digits , [ "." , digits ] | "." , digits ;
digits         = digit , { digit } ;
digit          = "0" | "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9" ;
field          = one of ALLOWED_FIELDS (exact identifier match) ;
```

Whitespace between tokens is permitted. Field names are case-sensitive and
must match the canonical snake_case names exactly. Standard precedence is
unary sign, then multiplication/division, then addition/subtraction. Binary
operators associate left-to-right; parentheses override precedence. Decimal
and integer literals are allowed, with no scientific notation in the Week 1
language definition. Unary minus allows negative values (e.g. `-pass_yards`).

**Disallowed:** arbitrary Python, functions (`sqrt(...)`), attribute access,
indexing, exponentiation, comparisons, strings, booleans, implicit multiplication,
unknown identifiers, and identity fields (`player_id`, `player_name`, `position`,
`season`). An implementation must parse a restricted AST, **never call `eval`**.

Proposed safety limits for Week 3 enforcement: maximum 256 characters,
20 AST levels, and numeric constants with absolute magnitude at most 1e9.
The parser must reject excessive nesting and non-finite constants with a
readable error. In calculation, missing source values, division by zero, and
non-finite outputs produce an unavailable value with a reason; they must never
be silently turned into zero. Numeric values are calculated from season totals
before any display rounding.

## Canonical fields

These names, descriptions, and units are defined *once* in
`backend/statforge/ingest/fields.py` and are exposed with
`formula_field_dictionary()`. Their precise wording may be refined with the
data-source owner when the historical snapshot is confirmed.

| Field | Unit | Meaning |
|---|---|---|
| `games` | games | Regular-season games with a recorded snap |
| `pass_attempts` | attempts | Forward passes thrown |
| `pass_yards` | yards | Net yards gained on completed passes |
| `pass_td` | touchdowns | Touchdown passes thrown |
| `interceptions` | count | Passes thrown that were intercepted |
| `carries` | attempts | Rushing attempts |
| `rush_yards` | yards | Net yards gained on carries |
| `receptions` | catches | Passes caught |
| `targets` | targets | Passes thrown to the player |
| `rec_yards` | yards | Net yards gained on receptions |

All ten are numeric per-player, per-regular-season totals. Rates are calculated
by formula rather than imported as per-game averages. This matters for traded
players and other aggregated data.

## Example and expected output

**QB Score:** `(pass_yards + 25 * pass_td - 40 * interceptions) / pass_attempts`

With 3,000 passing yards, 20 passing TDs, 10 interceptions, and 400 attempts,
the result is **7.75**. A zero-attempt season produces an unavailable value,
not infinity or a rank. The example is exploratory, not a validated measure of
QB quality. Users will eventually select higher- or lower-first ranking in the UI.

## Ownership / integration

- **Jo (API + ingestion):** use `STAT_FIELDS` / `STAT_FIELD_NAMES` for `/fields`;
  `formula_field_dictionary()` provides a serialization-friendly representation.
- **Krish (frontend):** display `label`, `definition`, and `unit`; insert the `name`
  token into the editor and show `QB_SCORE` as an example.
- **Ayush (formula engine):** in Week 3, enforce this vocabulary and grammar
  with `ast.parse(..., mode="eval")` and an explicit AST allowlist, accepting
  only numeric constants, names, `+ - * /`, unary `+ -`, and parentheses. Forbid
  all other AST nodes. Week 4 adds ranking and exclusion handling.

Use `cd backend && pytest tests/test_formula_grammar.py` to check this contract.
