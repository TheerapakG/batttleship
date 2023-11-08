from dataclasses import dataclass
from uuid import UUID

from . import models


@dataclass(eq=True, frozen=True)
class ObstacleVariant(models.ObstacleVariantId):
    name: str


ROCK_OBSTACLE_VARIANT = ObstacleVariant(
    UUID("03923ea8-2b21-4360-8e77-56ef37fcd099"),
    "rock",
)

OBSTACLE_VARIANTS = {
    ROCK_OBSTACLE_VARIANT.id: ROCK_OBSTACLE_VARIANT,
}
