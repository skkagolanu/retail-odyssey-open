import asyncio

from src.agents.contracts import AgentContext
from src.providers import OllamaProvider, normalize_image


class VisionAgent:
    def __init__(self, model: OllamaProvider):
        self.model = model

    async def run(self, context: AgentContext, image: str) -> tuple[str, dict]:
        normalized = await asyncio.to_thread(normalize_image, image)
        return await self.model.vision(context.message, normalized)
