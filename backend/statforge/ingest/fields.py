"""Canonical field names every data source is mapped onto.

These names are what the formula engine and the API see, so they must not
depend on any particular provider's column names. Definitions and units back
the field dictionary (R1); wording is owned by the formula-engine work and can
be refined here without touching any source adapter.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    definition: str
    unit: str
    kind: Literal["identity", "stat"]


IDENTITY_FIELDS: tuple[Field, ...] = (
    Field("player_id", "Player ID", "Stable identifier for the player.", "id", "identity"),
    Field("player_name", "Player", "Player's display name.", "text", "identity"),
    Field("position", "Position", "Primary position: QB, RB, WR or TE.", "text", "identity"),
    Field("season", "Season", "NFL season year (regular season only).", "year", "identity"),
)

STAT_FIELDS: tuple[Field, ...] = (
    Field("games", "Games played", "Regular-season games with a recorded snap.", "games", "stat"),
    Field("pass_attempts", "Passing attempts", "Forward passes thrown.", "attempts", "stat"),
    Field("pass_yards", "Passing yards", "Net yards gained on completed passes.", "yards", "stat"),
    Field("pass_td", "Passing touchdowns", "Touchdown passes thrown.", "touchdowns", "stat"),
    Field(
        "interceptions", "Interceptions", "Passes thrown that were intercepted.", "count", "stat"
    ),
    Field("carries", "Carries", "Rushing attempts.", "attempts", "stat"),
    Field("rush_yards", "Rushing yards", "Net yards gained on carries.", "yards", "stat"),
    Field("receptions", "Receptions", "Passes caught.", "catches", "stat"),
    Field("targets", "Targets", "Passes thrown to the player.", "targets", "stat"),
    Field("rec_yards", "Receiving yards", "Net yards gained on receptions.", "yards", "stat"),
)

ALL_FIELDS: tuple[Field, ...] = IDENTITY_FIELDS + STAT_FIELDS
FIELD_NAMES: tuple[str, ...] = tuple(f.name for f in ALL_FIELDS)
STAT_FIELD_NAMES: tuple[str, ...] = tuple(f.name for f in STAT_FIELDS)
