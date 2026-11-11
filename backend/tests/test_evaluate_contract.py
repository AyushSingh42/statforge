"""Strict input shapes for the API integration boundary."""

import pytest
from pydantic import ValidationError

from statforge.api.evaluate_contract import EvaluateRequest, Minimums
from statforge.config import SUPPORTED_POSITIONS


@pytest.mark.parametrize("raw", [{"games": 0}, {"games": 16, "targets": 50}, {}])
def test_active_minimums_keep_zero_and_skip_null(raw):
    assert Minimums(**raw).active() == raw


def test_request_defaults_and_serialization():
    request = EvaluateRequest(formula="games", seasons=[2020])
    assert request.positions == list(SUPPORTED_POSITIONS)
    assert request.minimums.active() == {}
    assert request.higher_is_better is True
    assert EvaluateRequest.model_validate_json(request.model_dump_json()) == request
    assert EvaluateRequest.model_json_schema()["additionalProperties"] is False


def test_default_lists_are_not_shared():
    first = EvaluateRequest(formula="games", seasons=[2020])
    first.positions.clear()
    assert EvaluateRequest(formula="games", seasons=[2020]).positions == list(SUPPORTED_POSITIONS)


@pytest.mark.parametrize(
    "overrides",
    [
        {"seasons": []},
        {"seasons": [2015]},
        {"seasons": [2026]},
        {"seasons": [2020, 2020]},
        {"seasons": ["2020"]},
        {"seasons": [True]},
        {"seasons": [2020.0]},
        {"seasons": "2020"},
        {"positions": []},
        {"positions": ["QB", "QB"]},
        {"positions": ["qb"]},
        {"positions": ["K"]},
        {"positions": "QB"},
        {"formula": ""},
        {"formula": " \t "},
        {"formula": "1" * 257},
        {"formula": 12},
        {"higher_is_better": "false"},
        {"higher_is_better": 0},
        {"minimums": {"games": -1}},
        {"minimums": {"games": "2"}},
        {"minimums": {"games": True}},
        {"minimums": {"games": 2.5}},
        {"minimums": {"receptions": 2}},
        {"min_games": 2},
        {"stats": {"games": 16}},
    ],
)
def test_bad_contract_inputs_are_rejected(overrides):
    with pytest.raises(ValidationError):
        EvaluateRequest.model_validate({"formula": "games", "seasons": [2020], **overrides})
