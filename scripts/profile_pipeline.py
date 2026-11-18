"""Profile ten deterministic catalogue agent turns; no remote providers or load test."""

import asyncio
import cProfile
import io
import json
import pstats
from pathlib import Path

import httpx

from src.agents.group_chat_orchestrator import GroupChatOrchestrator
from src.catalogue import Catalogue
from src.providers import ComfyProvider, OllamaProvider
from src.schemas import SessionState
from src.settings import Settings
from src.utils.prometheus_metrics import Metrics


async def workload():
    config = Settings(_env_file=None, engine="catalogue")
    async with httpx.AsyncClient() as client:
        orchestrator = GroupChatOrchestrator(
            config,
            Catalogue(config.catalogue_path, config.allowed_retailers),
            OllamaProvider(config, client),
            ComfyProvider(config, client),
            Metrics(),
        )
        state = SessionState()
        for _index in range(10):
            result = await orchestrator.process_message("classic business outfit under £100", state)
            state.history = state.history[-20:]
            assert result["engine"] == "catalogue" and result["products"]


def main():
    profiler = cProfile.Profile()
    profiler.enable()
    asyncio.run(workload())
    profiler.disable()
    output = io.StringIO()
    pstats.Stats(profiler, stream=output).strip_dirs().sort_stats("cumulative").print_stats(35)
    Path("benchmarks/profile-catalogue.txt").write_text(
        "Ten in-process catalogue agent turns; includes Python/client startup. No actual HTTP/model, concurrency or ARM claims.\n"
        + output.getvalue().rstrip()
        + "\n"
    )
    print(
        json.dumps(
            {
                "turns": 10,
                "mode": "in-process catalogue",
                "report": "benchmarks/profile-catalogue.txt",
            }
        )
    )


if __name__ == "__main__":
    main()
