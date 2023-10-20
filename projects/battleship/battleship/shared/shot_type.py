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
    UUID("e4d85882-6ea9-11ee-b962-0242ac120002"),
    {
        (0, 0): ["", "", "", ""],
    },
    False,
    1,
    False
)

TWOBYTWO_SHOT_VARIANT = ShotTypeVariant(
    UUID("f0d39692-6ea9-11ee-b962-0242ac120002"),
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
    UUID("f0d39692-6ea9-11ee-b962-0242ac120002"),
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
