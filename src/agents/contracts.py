"""Immutable, explicitly scoped sequential handoff data. No agent owns session state."""

from dataclasses import dataclass

from src.schemas import Preferences, Turn


@dataclass(frozen=True)
class AgentContext:
    message: str
    preferences: Preferences
    history: tuple[Turn, ...]
    wardrobe_description: str = ""
    product_ids: tuple[str, ...] = ()
