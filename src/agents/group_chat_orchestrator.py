"""Five-agent sequential execution with explicit handoffs, shared budgets and trace events."""

import asyncio
import logging
import time
import uuid
from dataclasses import replace

from src.agents.contracts import AgentContext
from src.agents.conversation_agent import ConversationAgent
from src.agents.imagegen_agent import ImageGenAgent
from src.agents.intent_agent import IntentAgent
from src.agents.recommendation_agent import RecommendationAgent
from src.agents.vision_agent import VisionAgent
from src.budget import CURRENT_AGENT, CURRENT_BUDGET, TokenBudget
from src.catalogue import Catalogue
from src.providers import ComfyProvider, OllamaProvider, ProviderUnavailable, normalize_image
from src.schemas import SessionState, Stage, Turn
from src.settings import Settings
from src.utils.prometheus_metrics import Metrics

logger = logging.getLogger("retail")


class GroupChatOrchestrator:
    def __init__(
        self,
        config: Settings,
        catalogue: Catalogue,
        model: OllamaProvider,
        images: ComfyProvider,
        metrics: Metrics,
    ):
        self.config, self.catalogue, self.model, self.images, self.metrics = (
            config,
            catalogue,
            model,
            images,
            metrics,
        )
        self.intent_agent = IntentAgent()
        self.vision_agent = VisionAgent(model)
        self.recommendation_agent = RecommendationAgent(model)
        self.conversation_agent = ConversationAgent(model)
        self.image_agent = ImageGenAgent(images)

    grounded_reply = staticmethod(ConversationAgent.grounded_reply)

    async def process_message(
        self, message: str, state: SessionState, image: str | None = None
    ) -> dict:
        budget = TokenBudget()
        token = CURRENT_BUDGET.set(budget)
        try:
            return await self._execute(message, state, image, budget)
        finally:
            CURRENT_BUDGET.reset(token)

    async def _execute(self, message, state, image, budget):
        began = time.perf_counter()
        trace_id = uuid.uuid4().hex
        stages: list[Stage] = []
        events: list[dict] = []
        warnings: list[str] = []
        usage: list[dict] = []

        def record(name, started, mode, status="completed", handoff=()):
            duration = time.perf_counter() - started
            stages.append(Stage(name=name, duration_ms=round(duration * 1000, 3), status=status))
            event = dict(
                trace_id=trace_id,
                sequence=len(events) + 1,
                agent=name,
                mode=mode,
                status=status,
                duration_ms=round(duration * 1000, 3),
                handoff_keys=list(handoff),
            )
            events.append(event)
            self.metrics.stage_latency.labels(stage=name).observe(duration)
            self.metrics.agent_runs.labels(agent=name, mode=mode, status=status).inc()
            if status == "unavailable":
                self.metrics.errors.labels(stage=name).inc()
            self.metrics.log(event)

        async def invoke(name, mode, call, handoff):
            started = time.perf_counter()
            agent_token = CURRENT_AGENT.set(name)
            status = "completed"
            try:
                return await call()
            except ProviderUnavailable:
                status = "unavailable"
                raise
            except (ValueError, TimeoutError, asyncio.CancelledError):
                status = "failed"
                raise
            finally:
                CURRENT_AGENT.reset(agent_token)
                record(name, started, mode, status, handoff)

        started = time.perf_counter()
        intent = self.intent_agent.run(message, state.preferences, has_image=image is not None)
        record("intent", started, "rules", handoff=("route", "preferences", "invocation_plan"))
        context = AgentContext(
            message,
            intent.preferences.model_copy(deep=True),
            tuple(turn.model_copy(deep=True) for turn in state.history[-8:]),
            state.wardrobe_context,
        )
        products, generated_image, engine = [], None, "catalogue"
        if intent.kind != "fashion":
            started = time.perf_counter()
            answer = {
                "greeting": "Hi! Tell me the occasion, style and outfit budget you have in mind. I can help choose from the catalogue.",
                "about": "I'm Retail Odyssey Open, a multi-agent fashion assistant. The intent agent plans each turn; vision, catalogue recommendation, conversation and image agents run when needed, passing bounded context sequentially. Optional local Ollama handles constrained selection, styling plans and image descriptions; product facts remain catalogue-grounded. Catalogue mode works without API keys. I cannot confirm live stock.",
                "out_of_scope": "I can help with clothing, outfits and the catalogue. That request is outside this assistant's scope.",
            }[intent.kind]
            record("conversation", started, "local", handoff=("reply",))
        else:
            state.preferences = intent.preferences
            if image:
                state.wardrobe_context = ""
                if self.config.engine == "ollama":
                    try:
                        description, counts = await invoke(
                            "vision",
                            "model",
                            lambda: self.vision_agent.run(context, image),
                            ("wardrobe_description",),
                        )
                        state.wardrobe_context = description
                        usage.append(dict(agent="vision", **counts))
                    except ProviderUnavailable:
                        warnings.append(
                            "Wardrobe analysis is unavailable. I have not inferred any items from your image."
                        )
                else:

                    async def validate_only():
                        await asyncio.to_thread(normalize_image, image)

                    await invoke("vision", "validation_only", validate_only, ())
                    warnings.append(
                        "Wardrobe image analysis requires the optional local vision model. No image analysis was performed."
                    )
                context = replace(context, wardrobe_description=state.wardrobe_context)
            started = time.perf_counter()
            products = self.catalogue.search(
                message + " " + context.wardrobe_description, state.preferences
            )
            if not products and state.recommendation_ids and "cheaper" not in message.lower():
                products = [
                    self.catalogue.by_id[key]
                    for key in state.recommendation_ids
                    if key in self.catalogue.by_id
                ]
                if state.preferences.budget_gbp is not None and sum(
                    p.price_pence for p in products
                ) > round(state.preferences.budget_gbp * 100):
                    products = []
            record("retrieval", started, "catalogue", handoff=("candidate_records",))
            model_selected = False
            try:
                use_model = self.config.engine == "ollama" and bool(products)
                products, counts = await invoke(
                    "recommendation",
                    "model" if use_model else "catalogue",
                    lambda: self.recommendation_agent.run(
                        context, products, self.catalogue.data.mode, use_model=use_model
                    ),
                    ("selected_product_ids",),
                )
                if use_model:
                    usage.append(dict(agent="recommendation", **counts))
                    model_selected, engine = True, "ollama"
            except ProviderUnavailable:
                warnings.append(
                    "The local model was unavailable or returned unvalidated output. This reply uses only the same catalogue records."
                )
            context = replace(context, product_ids=tuple(p.id for p in products))
            try:
                answer, counts = await invoke(
                    "conversation",
                    "model" if model_selected and products else "local",
                    lambda: self.conversation_agent.run(
                        context,
                        products,
                        sample=self.catalogue.data.mode == "sample",
                        use_model=model_selected,
                    ),
                    ("constrained_styling_plan", "reply"),
                )
                if counts:
                    usage.append(dict(agent="conversation", **counts))
            except ProviderUnavailable:
                answer = self.grounded_reply(products, sample=self.catalogue.data.mode == "sample")
                warnings.append(
                    "The conversation agent was unavailable; the validated selection is shown with a catalogue-only reply."
                )
            if intent.visualize:
                if self.images.configured and products:
                    try:
                        generated_image = await invoke(
                            "image",
                            "tool",
                            lambda: self.image_agent.run(context, products),
                            ("validated_image",),
                        )
                    except (ProviderUnavailable, OSError):
                        warnings.append(
                            "Image generation is unavailable. No generated image has been produced; the product layout is a schematic moodboard."
                        )
                else:
                    started = time.perf_counter()
                    record("image", started, "schematic", "unavailable")
                    warnings.append(
                        "Generative images are not configured. The product layout is a schematic moodboard, not an AI-generated photo or a product photograph."
                    )
            state.recommendation_ids = [p.id for p in products]
            state.conversation_state = intent.kind
        state.history.extend(
            [Turn(role="user", content=message), Turn(role="assistant", content=answer)]
        )
        for item in budget.calls:
            self.metrics.tokens.labels(agent=item["agent"], kind="reserved_output").inc(
                item["reserved_output_tokens"]
            )
            for key, kind in [
                ("prompt_eval_count", "reported_input"),
                ("eval_count", "reported_output"),
            ]:
                if isinstance(item["usage"].get(key), int):
                    self.metrics.tokens.labels(agent=item["agent"], kind=kind).inc(
                        item["usage"][key]
                    )
        return dict(
            answer=answer,
            products=[p.model_dump(mode="json") for p in products],
            catalogue=self.catalogue.info(),
            preferences=state.preferences.model_dump(),
            warnings=warnings,
            image=generated_image,
            image_kind="generated" if generated_image else "schematic",
            engine=engine,
            route=intent.kind,
            trace_id=trace_id,
            agent_trace=events,
            token_budget=budget.report(),
            timings=dict(
                total_ms=round((time.perf_counter() - began) * 1000, 3),
                stages=[stage.model_dump() for stage in stages],
            ),
            token_usage=usage,
        )
