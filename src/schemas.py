"""Strict public contracts; products come from the catalogue, never model-generated fields."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Preferences(StrictModel):
    occasion: str | None = Field(default=None, max_length=40)
    style: str | None = Field(default=None, max_length=40)
    budget_gbp: float | None = Field(default=None, ge=0, le=10000, allow_inf_nan=False)


class ChatRequest(StrictModel):
    message: str = Field(min_length=1, max_length=2000)
    image: str | None = Field(default=None, max_length=5_500_000)


class Turn(StrictModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=6000)


class SessionState(StrictModel):
    history: list[Turn] = Field(default_factory=list)
    preferences: Preferences = Field(default_factory=Preferences)
    wardrobe_context: str = Field(default="", max_length=1500)
    recommendation_ids: list[str] = Field(default_factory=list, max_length=3)
    conversation_state: str = Field(default="initial", max_length=40)


class Stage(StrictModel):
    name: Literal[
        "intent", "retrieval", "vision", "generation", "image", "recommendation", "conversation"
    ]
    duration_ms: float
    status: Literal["completed", "unavailable", "failed"] = "completed"


class ModelAnswer(StrictModel):
    answer: str = Field(min_length=1, max_length=3000)
    product_ids: list[str] = Field(default_factory=list, max_length=3)


class VisionAnswer(StrictModel):
    description: str = Field(min_length=1, max_length=1500)


class ModelSelection(StrictModel):
    product_ids: list[str] = Field(max_length=3)


class ConversationPlan(StrictModel):
    advice: Literal["coordinate_colours", "check_fit", "consider_layers", "keep_simple"]
    follow_up: Literal["colour", "fit", "none"]
