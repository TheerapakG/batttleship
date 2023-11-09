from dataclasses import dataclass
from uuid import UUID

from . import models


@dataclass(eq=True, frozen=True)
class AvatarVariant(models.AvatarVariantId):
    name: str


CAPTAIN_AVATAR_VARIANT = AvatarVariant(
    UUID("df2c420f-9b6b-4b73-a164-d80bc39a2df8"), "avatar/captain.png"
)

GIGACHAD_AVATAR_VARIANT = AvatarVariant(
    UUID("eac6ece6-d369-4c8b-a167-11708e16f1e3"),
    "avatar/gigachad.png",
)

GINGERMAN_AVATAR_VARIANT = AvatarVariant(
    UUID("7d6317f1-f3c3-4835-a4bf-425aa6bfe404"),
    "avatar/gingerman.png",
)

AVATAR_VARIANTS = {
    CAPTAIN_AVATAR_VARIANT.id: CAPTAIN_AVATAR_VARIANT,
    GIGACHAD_AVATAR_VARIANT.id: GIGACHAD_AVATAR_VARIANT,
    GINGERMAN_AVATAR_VARIANT.id: GINGERMAN_AVATAR_VARIANT,
}
