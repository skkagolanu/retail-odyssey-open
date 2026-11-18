"""Small deterministic router; avoids a paid call just to select a stage."""

import re
from dataclasses import dataclass

from src.schemas import Preferences


@dataclass
class Intent:
    kind: str
    preferences: Preferences
    recommend: bool
    visualize: bool


def parse_intent(message: str, current: Preferences, *, has_image: bool) -> Intent:
    lowered = message.lower().strip()
    updated = current.model_copy(deep=True)
    for word in ["casual", "formal", "business", "party", "workout", "wedding", "date"]:
        if re.search(r"\b" + word + r"\b", lowered):
            updated.occasion = word
            break
    for word in ["classic", "minimalist", "streetwear", "bold", "sporty"]:
        if re.search(r"\b" + word + r"\b", lowered):
            updated.style = word
            break
    budget = re.search(
        r"(?:£\s*|\b(?:budget|under|below|up.to)\s*(?:is\s*)?(?:GBP\s*)?)(\d+(?:\.\d{1,2})?)",
        message,
        re.I,
    )
    if budget:
        value = float(budget[1])
        if value <= 10000:
            updated.budget_gbp = value
    if not budget and re.search(r"\bcheaper\b", lowered) and current.budget_gbp is not None:
        updated.budget_gbp = round(current.budget_gbp * 0.8, 2)
    about = bool(
        re.search(
            r"\b(?:what (?:do you do|are you|can you do)|how (?:do you work|are you built)|your (?:sources|models|purpose))\b",
            lowered,
        )
    )
    greeting = bool(re.fullmatch(r"(?:hi|hello|hey|good (?:morning|evening))[!.\s]*", lowered))
    shopping = bool(
        re.search(
            r"\b(?:outfit|wear|style|fashion|clothes|clothing|shirt|trousers|jacket|shoes|dress|jeans|recommend|suggest|budget|formal|casual|wedding|workout|show|visuali[sz]e|picture)\b",
            lowered,
        )
    )
    followup = bool(
        re.search(
            r"\b(?:cheaper|another|alternative|instead|match|these|those|it|them|blue|red|green|navy|black|white|relaxed|tailored)\b",
            lowered,
        )
    ) and bool(current.occasion or current.style or current.budget_gbp is not None)
    unrelated = bool(
        re.search(
            r"\b(?:recipe|cook|code|program|crypto|stock.market|medical|diagnos|politic)\b", lowered
        )
    )
    kind = (
        "about"
        if about
        else "greeting"
        if greeting
        else "fashion"
        if (shopping or followup or has_image) and not unrelated
        else "out_of_scope"
    )
    visualize = kind == "fashion" and bool(
        re.search(r"\b(?:visuali[sz]e|picture|generate.image|show.*look|moodboard)\b", lowered)
    )
    return Intent(
        kind,
        updated if kind == "fashion" else current.model_copy(deep=True),
        kind == "fashion",
        visualize,
    )


class IntentAgent:
    """Deterministic planning agent; cheap local turns require no LLM call."""

    def run(self, message: str, current: Preferences, *, has_image: bool) -> Intent:
        return parse_intent(message, current, has_image=has_image)
