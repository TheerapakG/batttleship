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


NORMAL_NAVY_SHIP_VARIANT = ShipVariant(
    UUID("0a0000b1-f60b-4a62-9ae4-a718a8ada0cd"),
    {
        (0, 0): ["", "", "", ""],
        (1, 0): ["", "", "", ""],
        (2, 0): ["", "", "", ""],
        (3, 0): ["", "", "", ""],
    },
)

T_NAVY_SHIP_VARIANT = ShipVariant(
    UUID("e544f063-bba5-42ad-830e-20739640f5ec"),
    {
        (0, 0): ["", "", "", ""],
        (1, 0): ["", "", "", ""],
        (2, 0): ["", "", "", ""],
        (1, 1): ["", "", "", ""],
    },
)

NORMAL_SCOUT_SHIP_VARIANT = ShipVariant(
    UUID("5b077ee9-3a0b-4f63-a035-5cdfbaa27329"),
    {
        (0, 0): ["", "", "", ""],
        (1, 0): ["", "", "", ""],
        (2, 0): ["", "", "", ""],
        (3, 0): ["", "", "", ""],
    },
)

T_SCOUT_SHIP_VARIANT = ShipVariant(
    UUID("90646656-8633-495f-bdd9-9bfc25f564e3"),
    {
        (0, 0): ["", "", "", ""],
        (1, 0): ["", "", "", ""],
        (2, 0): ["", "", "", ""],
        (1, 1): ["", "", "", ""],
    },
)

NORMAL_PIRATE_SHIP_VARIANT = ShipVariant(
    UUID("f57f1c61-8016-4388-929f-62bcdf3b8206"),
    {
        (0, 0): ["", "", "", ""],
        (1, 0): ["", "", "", ""],
        (2, 0): ["", "", "", ""],
        (3, 0): ["", "", "", ""],
    },
)

T_PIRATE_SHIP_VARIANT = ShipVariant(
    UUID("7468d725-6429-4622-8867-b8333210cd71"),
    {
        (0, 0): ["", "", "", ""],
        (1, 0): ["", "", "", ""],
        (2, 0): ["", "", "", ""],
        (1, 1): ["", "", "", ""],
    },
)

SHIP_VARIANTS = {
    NORMAL_NAVY_SHIP_VARIANT.id: NORMAL_NAVY_SHIP_VARIANT,
    T_NAVY_SHIP_VARIANT.id: T_NAVY_SHIP_VARIANT,
    NORMAL_SCOUT_SHIP_VARIANT.id: NORMAL_SCOUT_SHIP_VARIANT,
    T_SCOUT_SHIP_VARIANT.id: T_SCOUT_SHIP_VARIANT,
    NORMAL_PIRATE_SHIP_VARIANT.id: NORMAL_PIRATE_SHIP_VARIANT,
    T_PIRATE_SHIP_VARIANT.id: T_PIRATE_SHIP_VARIANT,
}


SHIP_SKIN_LOOKUP = {
    "Navy": [
        NORMAL_NAVY_SHIP_VARIANT,
        NORMAL_NAVY_SHIP_VARIANT,
        T_NAVY_SHIP_VARIANT,
        T_NAVY_SHIP_VARIANT,
    ],
    "Scout": [
        NORMAL_SCOUT_SHIP_VARIANT,
        NORMAL_SCOUT_SHIP_VARIANT,
        T_SCOUT_SHIP_VARIANT,
        T_SCOUT_SHIP_VARIANT,
    ],
    "Pirate": [
        NORMAL_PIRATE_SHIP_VARIANT,
        NORMAL_PIRATE_SHIP_VARIANT,
        T_PIRATE_SHIP_VARIANT,
        T_PIRATE_SHIP_VARIANT,
    ],
}
