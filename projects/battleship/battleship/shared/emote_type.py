from dataclasses import dataclass
from uuid import UUID

from . import models


@dataclass(eq=True, frozen=True)
class EmoteVariant(models.EmoteVariantId):
    name: str


HELLO_EMOTE_VARIANT = EmoteVariant(
    UUID("ba2e0d83-8f6a-4417-907a-8c8fd30e206b"),
    "emote/hello.png",
)

BYE_EMOTE_VARIANT = EmoteVariant(
    UUID("93fed1a6-c000-49b8-8173-347934f1427d"),
    "emote/bye.png",
)

ANGRY_EMOTE_VARIANT = EmoteVariant(
    UUID("d1891a0c-6eb1-40d2-a703-5769e84e03fb"),
    "emote/angry.png",
)

BRUH_EMOTE_VARIANT = EmoteVariant(
    UUID("60ae3104-79aa-4043-97a9-7f1c5a0a376f"),
    "emote/bruh.png",
)

EXCLAIM_EMOTE_VARIANT = EmoteVariant(
    UUID("aa22a398-da36-4653-b319-78c6f2890aa5"),
    "emote/exclaim.png",
)

QUESTION_EMOTE_VARIANT = EmoteVariant(
    UUID("4c76d27f-8c21-47cc-9cde-fa5cc79aba7b"),
    "emote/question.png",
)

EMOTE_VARIANTS = {
    HELLO_EMOTE_VARIANT.id: HELLO_EMOTE_VARIANT,
    BYE_EMOTE_VARIANT.id: BYE_EMOTE_VARIANT,
    ANGRY_EMOTE_VARIANT.id: ANGRY_EMOTE_VARIANT,
    BRUH_EMOTE_VARIANT.id: BRUH_EMOTE_VARIANT,
    EXCLAIM_EMOTE_VARIANT.id: EXCLAIM_EMOTE_VARIANT,
    QUESTION_EMOTE_VARIANT.id: QUESTION_EMOTE_VARIANT,
}
