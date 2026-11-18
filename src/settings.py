"""Application configuration; no external service is required for catalogue mode."""

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RO_", env_file=".env", extra="ignore", hide_input_in_errors=True
    )
    engine: Literal["catalogue", "ollama", "cloudflare"] = "catalogue"
    database_path: Path = ROOT / "var/sessions.sqlite3"
    catalogue_path: Path = ROOT / "data/catalogue.json"
    allowed_retailers: tuple[str, ...] = (
        "sportsdirect.com",
        "houseoffraser.co.uk",
        "flannels.com",
        "usc.co.uk",
        "jackwills.com",
    )
    allowed_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    )
    trusted_hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "testserver")
    secure_cookies: bool = False
    session_ttl_seconds: int = Field(default=86400, ge=60, le=604800)
    max_sessions: int = Field(default=1000, ge=1, le=100000)
    max_history_messages: int = Field(default=20, ge=2, le=100, multiple_of=2)
    max_session_requests_per_minute: int = Field(default=20, ge=1, le=120)
    max_inflight: int = Field(default=4, ge=1, le=16)
    max_body_bytes: int = Field(default=6_000_000, ge=1024, le=10_000_000)
    request_timeout_seconds: float = Field(default=90, gt=0, le=120)
    provider_timeout_seconds: float = Field(default=60, gt=0, le=60)
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3-vl:4b-instruct"
    ollama_threads: int = Field(default=2, ge=1, le=16)
    cloudflare_account_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    cloudflare_api_token: SecretStr | None = None
    cloudflare_free_plan_confirmed: bool = False
    cloudflare_model: Literal["@cf/qwen/qwen3.8-27b"] = "@cf/qwen/qwen3.8-27b"
    cloudflare_image_model: Literal["@cf/black-forest-labs/flux-1-schnell"] = (
        "@cf/black-forest-labs/flux-1-schnell"
    )
    comfyui_url: str | None = None
    comfyui_workflow: Path | None = None

    @field_validator("allowed_origins")
    @classmethod
    def explicit_origins(cls, origins: tuple[str, ...]) -> tuple[str, ...]:
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
                or "*" in origin
            ):
                raise ValueError("Configure exact HTTP(S) origins, without wildcards")
        return tuple(origin.rstrip("/") for origin in origins)

    @field_validator("ollama_url", "comfyui_url")
    @classmethod
    def provider_url(cls, value: str | None) -> str | None:
        if value is not None:
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("Provider URL must be an administrator-configured HTTP(S) origin")
            return value.rstrip("/")
        return None

    @model_validator(mode="after")
    def cloud_configuration(self):
        if self.engine == "cloudflare" and not (
            self.cloudflare_account_id
            and self.cloudflare_api_token
            and self.cloudflare_api_token.get_secret_value().strip()
            and self.cloudflare_free_plan_confirmed
        ):
            raise ValueError(
                "Cloud mode requires Cloudflare account configuration and confirmation that Workers Free is selected"
            )
        return self
