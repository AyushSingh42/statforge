"""Request contract for Jo's POST /evaluate route; this module registers no routes.

Formula parsing and row results live in statforge.formula. Jo owns data selection,
HTTP handling and the final leaderboard envelope. See Docs/evaluate-contract.md.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from statforge.config import SUPPORTED_POSITIONS, SUPPORTED_SEASONS
from statforge.formula.grammar import MAX_FORMULA_LENGTH

NonnegativeInt = Annotated[int, Field(ge=0)]


class Minimums(BaseModel):
    """All active (non-null) thresholds are inclusive and combined with AND."""

    model_config = ConfigDict(extra="forbid", strict=True)

    games: NonnegativeInt | None = None
    pass_attempts: NonnegativeInt | None = None
    carries: NonnegativeInt | None = None
    targets: NonnegativeInt | None = None

    def active(self) -> dict[str, int]:
        """Canonical field -> threshold; zero is active, None is disabled."""
        return self.model_dump(exclude_none=True)


class EvaluateRequest(BaseModel):
    """Typed selection criteria plus a formula; never accepts client-supplied data."""

    model_config = ConfigDict(extra="forbid", strict=True)

    formula: str = Field(min_length=1, max_length=MAX_FORMULA_LENGTH)
    seasons: list[int] = Field(min_length=1, max_length=len(SUPPORTED_SEASONS))
    positions: list[str] = Field(
        default_factory=lambda: list(SUPPORTED_POSITIONS),
        min_length=1,
        max_length=len(SUPPORTED_POSITIONS),
    )
    minimums: Minimums = Field(default_factory=Minimums)
    higher_is_better: bool = True

    @field_validator("formula")
    @classmethod
    def nonblank_formula(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Enter a formula before evaluating it.")
        return value

    @field_validator("seasons")
    @classmethod
    def valid_seasons(cls, values: list[int]) -> list[int]:
        if len(values) != len(set(values)):
            raise ValueError("Seasons must not contain duplicates.")
        if any(value not in SUPPORTED_SEASONS for value in values):
            raise ValueError(f"Choose supported seasons: {SUPPORTED_SEASONS}.")
        return values

    @field_validator("positions")
    @classmethod
    def valid_positions(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("Positions must not contain duplicates.")
        if any(value not in SUPPORTED_POSITIONS for value in values):
            raise ValueError(f"Choose supported positions: {SUPPORTED_POSITIONS}.")
        return values
