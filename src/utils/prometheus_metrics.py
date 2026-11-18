"""Metrics have literal meanings and bounded labels; no chat content/session IDs."""

import json
import logging
import os
from collections import deque
from threading import Lock

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram


class Metrics:
    def __init__(self):
        self.recent_events: deque[dict] = deque(maxlen=200)
        self.lock = Lock()
        logger = logging.getLogger("retail")
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        self.registry = CollectorRegistry()
        self.agent_runs = Counter(
            "retail_agent_runs_total",
            "Agent invocations by mode and outcome",
            ["agent", "mode", "status"],
            registry=self.registry,
        )
        self.tokens = Counter(
            "retail_model_tokens_total",
            "Reserved upper bounds and actual provider-reported usage, separately labelled",
            ["agent", "kind"],
            registry=self.registry,
        )
        self.http = Counter(
            "retail_http_requests_total",
            "HTTP responses by normalized route",
            ["method", "route", "status"],
            registry=self.registry,
        )
        self.http_latency = Histogram(
            "retail_http_duration_seconds",
            "Full HTTP request completion including intent/model stages",
            ["route"],
            registry=self.registry,
        )
        self.sessions_created = Counter(
            "retail_sessions_created_total",
            "New server-issued browser sessions",
            registry=self.registry,
        )
        self.cleared = Counter(
            "retail_conversations_cleared_total",
            "Explicit conversation resets",
            registry=self.registry,
        )
        self.active = Gauge(
            "retail_active_sessions", "Unexpired stored browser sessions", registry=self.registry
        )
        self.products = Counter(
            "retail_products_returned_total",
            "Typed product cards actually returned in completed chat responses",
            registry=self.registry,
        )
        self.errors = Counter(
            "retail_provider_failures_total",
            "Local provider failures or rejected structured outputs",
            ["stage"],
            registry=self.registry,
        )
        self.stage_latency = Histogram(
            "retail_stage_duration_seconds",
            "Wall time for each requested stage",
            ["stage"],
            registry=self.registry,
        )

    def log(self, event: dict) -> None:
        # Strict fields supplied by the orchestrator; never serialize prompts/context.
        clean = {
            key: event[key]
            for key in [
                "trace_id",
                "sequence",
                "agent",
                "mode",
                "status",
                "duration_ms",
                "handoff_keys",
            ]
        }
        with self.lock:
            self.recent_events.append(clean)
        logging.getLogger("retail").info(
            json.dumps(dict(event="agent_completed", process_id=os.getpid(), **clean))
        )
