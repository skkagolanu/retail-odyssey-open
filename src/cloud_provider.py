"""Cloudflare Workers AI transports; existing agent schemas/validation remain in force.

No local model, paid-provider fallback, SDK dependency or remote user URL fetching.
"""

import asyncio

from src.budget import CURRENT_BUDGET, TokenBudget
from src.providers import (
    ComfyProvider,
    OllamaProvider,
    ProviderUnavailable,
    bounded_json,
    normalize_image,
)


class CloudflareProvider(OllamaProvider):
    """Reuse answer/compose/vision schema validation; replace all Ollama I/O."""

    @property
    def endpoint(self) -> str:
        return (
            f"https://api.cloudflare.com/client/v4/accounts/{self.config.cloudflare_account_id}/ai"
        )

    @property
    def headers(self) -> dict:
        token = self.config.cloudflare_api_token
        if not token:
            raise ProviderUnavailable("Cloud inference is not configured")
        return {"Authorization": "Bearer " + token.get_secret_value()}

    async def available(self) -> bool:
        try:
            result = await bounded_json(
                self.client,
                "GET",
                self.endpoint + "/models/search",
                headers=self.headers,
                params={"search": self.config.cloudflare_model},
                timeout=3,
            )
            models = result.get("result")
            return (
                result.get("success") is True
                and isinstance(models, list)
                and any(
                    isinstance(model, dict) and model.get("name") == self.config.cloudflare_model
                    for model in models
                )
            )
        except ProviderUnavailable:
            return False

    async def _chat(self, messages: list[dict], schema: dict) -> dict:
        budget = CURRENT_BUDGET.get() or TokenBudget(per_call_output=512, output_limit=1536)
        messages, output_limit, reservation = budget.prepare(messages, schema)
        converted = []
        for message in messages:
            converted_message = {key: value for key, value in message.items() if key != "images"}
            if message.get("images"):
                converted_message["content"] = [{"type": "text", "text": message["content"]}] + [
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + image}}
                    for image in message["images"]
                ]
            converted.append(converted_message)
        try:
            result = await bounded_json(
                self.client,
                "POST",
                self.endpoint + "/v1/chat/completions",
                headers=self.headers,
                json={
                    "model": self.config.cloudflare_model,
                    "messages": converted,
                    "stream": False,
                    "store": False,
                    "temperature": 0,
                    "max_completion_tokens": output_limit,
                    "reasoning_effort": "low",
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {"name": "agent_result", "strict": True, "schema": schema},
                    },
                },
            )
            choices = result.get("choices")
            if (
                not isinstance(choices, list)
                or not choices
                or not isinstance(choices[0], dict)
                or choices[0].get("finish_reason") != "stop"
            ):
                raise ProviderUnavailable("Cloud model did not finish its constrained result")
            final_message = choices[0].get("message")
            if (
                not isinstance(final_message, dict)
                or not isinstance(final_message.get("content"), str)
                or not final_message["content"].strip()
            ):
                raise ProviderUnavailable("Cloud model returned no final answer")
            usage = result.get("usage") or {}
            counts = {
                target: usage[source]
                for source, target in [
                    ("prompt_tokens", "prompt_eval_count"),
                    ("completion_tokens", "eval_count"),
                ]
                if isinstance(usage, dict)
                and isinstance(usage.get(source), int)
                and not isinstance(usage.get(source), bool)
                and usage[source] >= 0
            }
            reservation["status"] = "completed"
            reservation["usage"] = counts
            return {"content": final_message["content"], "usage": counts}
        except ProviderUnavailable as error:
            reservation["status"] = "unavailable"
            raise ProviderUnavailable(
                "Cloud inference is unavailable, quota-limited or returned an invalid response; no paid fallback was used"
            ) from error


class CloudflareImageProvider(ComfyProvider):
    """Same image-agent contract; server-side Workers AI replaces local ComfyUI."""

    @property
    def configured(self) -> bool:
        return bool(
            self.config.engine == "cloudflare"
            and self.config.cloudflare_api_token
            and self.config.cloudflare_account_id
            and self.config.cloudflare_free_plan_confirmed
        )

    async def generate(self, description: str) -> str:
        if not self.configured:
            raise ProviderUnavailable("Cloud image generation is not configured")
        token = self.config.cloudflare_api_token
        assert token is not None
        endpoint = f"https://api.cloudflare.com/client/v4/accounts/{self.config.cloudflare_account_id}/ai/run/{self.config.cloudflare_image_model}"
        result = await bounded_json(
            self.client,
            "POST",
            endpoint,
            max_bytes=6_000_000,
            headers={"Authorization": "Bearer " + token.get_secret_value()},
            json={"prompt": description[:2048], "steps": 4},
        )
        if result.get("success") is False:
            raise ProviderUnavailable("Cloud image generation is unavailable or quota-limited")
        body = result.get("result", result)
        encoded = body.get("image") if isinstance(body, dict) else None
        if not isinstance(encoded, str) or not encoded:
            raise ProviderUnavailable("Cloud image service returned no image")
        try:
            normalized = await asyncio.to_thread(
                normalize_image, "data:image/jpeg;base64," + encoded
            )
        except ValueError as error:
            raise ProviderUnavailable("Cloud image service returned invalid image bytes") from error
        return "data:image/jpeg;base64," + normalized
