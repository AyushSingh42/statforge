#!/usr/bin/env bash
# Run from anywhere after activating the backend's Python environment.
set -euo pipefail

if [[ $# -gt 1 || ( $# -eq 1 && "$1" != "--fix" ) ]]; then
  echo "Usage: bash scripts/check-ayush-part2.sh [--fix]" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"

# Limit automatic edits to this contribution, not teammates' unrelated files.
FILES=(
  statforge/formula
  statforge/api/evaluate_contract.py
  statforge/api/formula_demo.py
  tests/test_formula_parser.py
  tests/test_formula_evaluator.py
  tests/test_formula_integration.py
  tests/test_evaluate_contract.py
)

if [[ "${1:-}" == "--fix" ]]; then
  python -m ruff check --fix "${FILES[@]}"
  python -m ruff format "${FILES[@]}"
fi

python -m ruff check .
python -m ruff format --check .
python -m pytest
# Override project addopts so this coverage run measures ONLY the formula engine.
python -m pytest -o addopts="" tests/test_formula*.py \
  --cov=statforge.formula --cov-branch --cov-report=term-missing --cov-fail-under=90
