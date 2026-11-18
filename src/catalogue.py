"""Typed product snapshots and retailer-host validation, independent of model output."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, field_validator, model_validator

from src.schemas import Preferences, StrictModel


class Product(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    name: str = Field(min_length=1, max_length=100)
    brand: str = Field(min_length=1, max_length=60)
    retailer: str = Field(min_length=1, max_length=60)
    category: Literal["top", "bottom", "layer", "shoes", "accessory"]
    price_pence: int = Field(strict=True, ge=1, le=1_000_000)
    currency: Literal["GBP"] = "GBP"
    tags: list[str] = Field(min_length=1, max_length=20)
    url: str | None = Field(default=None, max_length=1000)
    captured_at: datetime

    @field_validator("tags")
    @classmethod
    def bounded_tags(cls, values: list[str]) -> list[str]:
        if any(not re.fullmatch(r"[a-z0-9-]{1,30}", value) for value in values):
            raise ValueError("Tags must be short lowercase terms")
        return list(dict.fromkeys(values))

    @field_validator("captured_at")
    @classmethod
    def explicit_snapshot_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value > datetime.now(UTC):
            raise ValueError("Capture time must be timezone-aware and not in the future")
        return value


class CatalogueFile(StrictModel):
    mode: Literal["sample", "snapshot"]
    description: str = Field(min_length=1, max_length=300)
    products: list[Product] = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({product.id for product in self.products}) != len(self.products):
            raise ValueError("Catalogue IDs must be unique")
        if self.mode == "sample" and any(product.url for product in self.products):
            raise ValueError("Sample products must not imply real purchase links")
        if self.mode == "snapshot" and any(not product.url for product in self.products):
            raise ValueError("Every snapshot product needs an attributable source URL")
        return self


def retailer_url(value: str, allowed: tuple[str, ...]) -> str:
    if any(ord(character) < 33 for character in value) or "\\" in value:
        raise ValueError("Invalid retailer URL")
    parsed = urlsplit(value)
    host = (parsed.hostname or "").encode("idna").decode("ascii").lower().rstrip(".")
    try:
        valid_port = parsed.port in {None, 443}
    except ValueError as error:
        raise ValueError("Invalid retailer URL") from error
    if (
        parsed.scheme != "https"
        or not valid_port
        or parsed.username
        or parsed.password
        or not any(host == domain or host.endswith("." + domain) for domain in allowed)
    ):
        raise ValueError("Product URL is outside the retailer allowlist")
    # Anchors are not source identity; preserve the verified host instead of raw netloc.
    return urlunsplit(("https", host, parsed.path or "/", parsed.query, ""))


class Catalogue:
    def __init__(self, path: Path, allowed: tuple[str, ...]):
        if path.stat().st_size > 10_000_000:
            raise ValueError("Catalogue file exceeds 10 MB")
        self.data = CatalogueFile.model_validate(json.loads(path.read_text()))
        for product in self.data.products:
            if product.url:
                product.url = retailer_url(product.url, allowed)
        self.by_id = {product.id: product for product in self.data.products}

    def search(self, query: str, preferences: Preferences, limit: int = 3) -> list[Product]:
        tokens = set(re.findall(r"[a-z]+", query.lower()))
        tags = {term for term in [preferences.occasion, preferences.style] if term}
        scored = []
        for product in self.data.products:
            if preferences.budget_gbp is not None and product.price_pence > round(
                preferences.budget_gbp * 100
            ):
                continue
            words = set(re.findall(r"[a-z]+", product.name.lower())) | set(product.tags)
            score = len(tokens & words) + 3 * len(tags & set(product.tags))
            if score:
                scored.append((score, product.id, product))
        scored.sort(key=lambda row: (-row[0], row[1]))
        selected: list[Product] = []
        for _, _, product in scored:
            if not any(item.category == product.category for item in selected):
                selected.append(product)
            if len(selected) == limit:
                break
        if not selected:
            selected = [row[2] for row in scored[:limit]]
        # A stated budget is an outfit-total cap, not a per-item promise.
        if preferences.budget_gbp is not None:
            budget = round(preferences.budget_gbp * 100)
            fitted = []
            for product in selected:
                if product.price_pence <= budget:
                    fitted.append(product)
                    budget -= product.price_pence
            selected = fitted
        return selected

    def info(self) -> dict:
        return dict(
            mode=self.data.mode,
            description=self.data.description,
            products=len(self.data.products),
            stock_verified=False,
        )


def validate_model_answer(answer: str, selected: list[Product]) -> bool:
    # Facts/actions live in typed cards. Generated styling prose cannot add a shop link,
    # currency claim or availability assertion that the snapshot cannot establish.
    if re.search(
        r"https?://|www\.|\]\(|[£€$]|\b(?:GBP|USD|EUR|in.stock|live.price|available.now|guaranteed)\b",
        answer,
        re.I,
    ):
        return False
    return bool(answer.strip()) and len(answer) <= 3000
