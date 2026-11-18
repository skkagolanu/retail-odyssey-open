from src.agents.contracts import AgentContext
from src.catalogue import Product
from src.providers import ComfyProvider


class ImageGenAgent:
    def __init__(self, provider: ComfyProvider):
        self.provider = provider

    async def run(self, context: AgentContext, products: list[Product]) -> str:
        # User prose is not executable workflow content; prompt is assembled from selected records.
        return await self.provider.generate(
            "Editorial illustration of an outfit, no logos or text: "
            + ", ".join(product.name for product in products)
        )
