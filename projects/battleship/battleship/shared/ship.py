from dataclasses import dataclass
from uuid import UUID

from . import models


@dataclass
class ShipVariant(models.ShipVariantId):
    placement_offsets: dict[tuple[int, int], str]


NORMAL_SHIP_VARIANT = ShipVariant(
    UUID("0a0000b1-f60b-4a62-9ae4-a718a8ada0cd"),
    {
        (0, 0): "",
        (1, 0): "",
        (2, 0): "",
        (3, 0): "",
    },
)

SHIP_VARIANTS = {NORMAL_SHIP_VARIANT.id: NORMAL_SHIP_VARIANT}
