from dataclasses import dataclass
from uuid import UUID

from . import models


@dataclass(eq=True, frozen=True)
class EmoteVariant(models.EmoteVariantId):
    name: str


HELLO_EMOTE_VARIANT = EmoteVariant(
    UUID("ba2e0d83-8f6a-4417-907a-8c8fd30e206b"),
    "hello",
)

BYE_EMOTE_VARIANT = EmoteVariant(
    UUID("93fed1a6-c000-49b8-8173-347934f1427d"),
    "bye",
)

EMOTE_VARIANTS = {
    HELLO_EMOTE_VARIANT.id: HELLO_EMOTE_VARIANT,
    BYE_EMOTE_VARIANT.id: BYE_EMOTE_VARIANT,
}
