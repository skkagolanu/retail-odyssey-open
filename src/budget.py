"""Per-turn model budgets, isolated by asyncio context; conservative text estimates."""

import json
from contextvars import ContextVar
from dataclasses import dataclass, field

from src.providers_errors import ProviderUnavailable

CURRENT_BUDGET: ContextVar["TokenBudget | None"] = ContextVar("retail_budget", default=None)
CURRENT_AGENT: ContextVar[str] = ContextVar("retail_agent", default="provider")


@dataclass
class TokenBudget:
    context_limit: int = 4096
    input_limit: int = 10000
    output_limit: int = 384
    per_call_output: int = 128
    reserved_input: int = 0
    reserved_output: int = 0
    calls: list[dict] = field(default_factory=list)

    def prepare(self, messages: list[dict], schema: dict) -> tuple[list[dict], int, dict]:
        # UTF-8 bytes are a deliberately conservative text proxy, not tokenizer counts.
        # Image tokens are model-dependent: reserve 2048 and verify reported use afterward.
        copied = [dict(message) for message in messages]
        image_reserve = 2048 if any(message.get("images") for message in copied) else 0

        def estimate():
            text = [
                {key: value for key, value in message.items() if key != "images"}
                for message in copied
            ]
            return (
                len(json.dumps(text, ensure_ascii=False).encode())
                + len(json.dumps(schema).encode())
                + 128
                + image_reserve
            )

        allowance = min(
            self.context_limit - self.per_call_output, self.input_limit - self.reserved_input
        )
        dropped = 0
        # Preserve the system prompt and current question; drop oldest complete history pairs.
        while estimate() > allowance and len(copied) > 2:
            copied[1:3] = []
            dropped += 2
        estimated = estimate()
        if estimated > allowance or self.reserved_output + self.per_call_output > self.output_limit:
            raise ProviderUnavailable("The model token budget was exhausted")
        self.reserved_input += estimated
        self.reserved_output += self.per_call_output
        record = dict(
            agent=CURRENT_AGENT.get(),
            estimated_input_tokens=estimated,
            reserved_output_tokens=self.per_call_output,
            dropped_history_messages=dropped,
            status="reserved",
            usage={},
        )
        self.calls.append(record)
        return copied, self.per_call_output, record

    def report(self) -> dict:
        return dict(
            context_limit=self.context_limit,
            turn_input_limit=self.input_limit,
            turn_output_limit=self.output_limit,
            reserved_input_tokens=self.reserved_input,
            reserved_output_tokens=self.reserved_output,
            estimator="UTF-8 byte upper-bound proxy plus fixed image reserve; actual model usage is reported separately",
            calls=self.calls,
        )
