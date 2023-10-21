from dataclasses import dataclass
from uuid import UUID

from . import models

ORINTATIONS = [
    ((1, 0), (0, 1)),
    ((0, -1), (1, 0)),
    ((-1, 0), (0, -1)),
    ((0, 1), (-1, 0)),
]


@dataclass
class ShotTypeVariant(models.ShotTypeVariantId):
    placement_offsets: dict[tuple[int, int], list[str]]
    random: bool
    number_of_shot: int
    orientation: bool


NORMAL_SHOT_VARIANT = ShotTypeVariant(
    UUID("618489a5-4a90-43de-9471-505e9f25d819"),
    {
        (0, 0): ["", "", "", ""],
    },
    False,
    1,
    False
)

TWOBYTWO_SHOT_VARIANT = ShotTypeVariant(
    UUID("c40445f1-da33-4b7b-aa92-9d20d8b254c8"),
    {
        (0, 0): ["", "", "", ""],
        (1, 0): ["", "", "", ""],
        (0, 1): ["", "", "", ""],
        (1, 1): ["", "", "", ""],
    },
    True,
    2,
    False
)

THREEROW_SHOT_VARIANT = ShotTypeVariant(
    UUID("2437ef52-4f01-40ea-8ea5-822b92327414"),
    {
        (0, 0): ["", "", "", ""],
        (1, 0): ["", "", "", ""],
        (2, 0): ["", "", "", ""],
    },
    True,
    2,
    True
)

SHOT_VARIANTS = {
    NORMAL_SHOT_VARIANT.id: NORMAL_SHOT_VARIANT,
    TWOBYTWO_SHOT_VARIANT.id: TWOBYTWO_SHOT_VARIANT,
    THREEROW_SHOT_VARIANT.id: THREEROW_SHOT_VARIANT,
}
