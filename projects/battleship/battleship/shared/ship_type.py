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
class ShipVariant(models.ShipVariantId):
    placement_offsets: dict[tuple[int, int], list[str]]


NORMAL_SHIP_VARIANT = ShipVariant(
    UUID("0a0000b1-f60b-4a62-9ae4-a718a8ada0cd"),
    {
        (0, 0): ["", "", "", ""],
        (1, 0): ["", "", "", ""],
        (2, 0): ["", "", "", ""],
        (3, 0): ["", "", "", ""],
    },
)

T_SHIP_VARIANT = ShipVariant(
    UUID("e544f063-bba5-42ad-830e-20739640f5ec"),
    {
        (0, 0): ["", "", "", ""],
        (1, 0): ["", "", "", ""],
        (2, 0): ["", "", "", ""],
        (1, 1): ["", "", "", ""],
    },
)

SHIP_VARIANTS = {
    NORMAL_SHIP_VARIANT.id: NORMAL_SHIP_VARIANT,
    T_SHIP_VARIANT.id: T_SHIP_VARIANT,
}