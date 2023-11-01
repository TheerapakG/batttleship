from dataclasses import dataclass
from uuid import UUID

from . import models

ORIENTATIONS = [
    ((1, 0), (0, 1)),
    ((0, -1), (1, 0)),
    ((-1, 0), (0, -1)),
    ((0, 1), (-1, 0)),
]


@dataclass(eq=True, frozen=True)
class ShotVariant(models.ShotVariantId):
    text: str
    placement_offsets: dict[tuple[int, int], list[str]]
    number_of_shot: int
    reveal: bool


NORMAL_SHOT_VARIANT = ShotVariant(
    UUID("618489a5-4a90-43de-9471-505e9f25d819"),
    "Normal",
    {
        (0, 0): ["", "", "", ""],
    },
    1,
    False,
)

TWOBYTWO_SHOT_VARIANT = ShotVariant(
    UUID("c40445f1-da33-4b7b-aa92-9d20d8b254c8"),
    "TWOBYTWO",
    {
        (0, 0): ["", "", "", ""],
        (1, 0): ["", "", "", ""],
        (0, 1): ["", "", "", ""],
        (1, 1): ["", "", "", ""],
    },
    2,
    False,
)

THREEROW_SHOT_VARIANT = ShotVariant(
    UUID("2437ef52-4f01-40ea-8ea5-822b92327414"),
    "THREEROW",
    {
        (0, 0): ["", "", "", ""],
        (1, 0): ["", "", "", ""],
        (2, 0): ["", "", "", ""],
    },
    2,
    False,
)

MINE = ShotVariant(
    UUID("27842c74-234a-4715-81f3-084a6f8aed16"),
    "MINE",
    {
        (0, 0): ["", "", "", ""],
    },
    1,
    False,
)

SCAN = ShotVariant(
    UUID("5b956aa8-c9b6-40d2-8b0f-3cbe47aeb50b"),
    "SCAN",
    {
        (0, 0): ["", "", "", ""],
        (1, 0): ["", "", "", ""],
        (0, 1): ["", "", "", ""],
        (1, 1): ["", "", "", ""],
    },
    4,
    True,
)

SHOT_VARIANTS = {
    NORMAL_SHOT_VARIANT.id: NORMAL_SHOT_VARIANT,
    TWOBYTWO_SHOT_VARIANT.id: TWOBYTWO_SHOT_VARIANT,
    THREEROW_SHOT_VARIANT.id: THREEROW_SHOT_VARIANT,
    MINE.id: MINE,
    SCAN.id: SCAN,
}
