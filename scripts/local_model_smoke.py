"""Opt-in two-request real local provider smoke, CPU thread limit two; not quality evidence."""

import asyncio
import base64
import io
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

from src.providers import OllamaProvider, ProviderUnavailable, normalize_image
from src.settings import Settings


async def main():
    config = Settings(
        _env_file=None,
        engine="ollama",
        ollama_model="qwen3-vl:2b-instruct",
        provider_timeout_seconds=60,
    )
    rows = []
    async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
        provider = OllamaProvider(config, client)
        for kind in ["chat", "vision"]:
            began = time.perf_counter()
            try:
                if kind == "chat":
                    result, usage = await provider.answer(
                        [
                            {
                                "role": "system",
                                "content": "Return JSON with product_ids only. Select only blue-shirt or sand-chinos.",
                            },
                            {"role": "user", "content": "Recommend a casual blue and sand outfit."},
                        ]
                    )
                    value = result.model_dump()
                else:
                    image = Image.new("RGB", (256, 256), "white")
                    draw = ImageDraw.Draw(image)
                    draw.polygon(
                        [
                            (80, 40),
                            (40, 70),
                            (55, 105),
                            (85, 90),
                            (85, 220),
                            (170, 220),
                            (170, 90),
                            (200, 105),
                            (215, 70),
                            (175, 40),
                        ],
                        fill="blue",
                    )
                    output = io.BytesIO()
                    image.save(output, format="PNG")
                    value, usage = await provider.vision(
                        "Describe only the visible garment and colour in one sentence.",
                        normalize_image(
                            "data:image/png;base64," + base64.b64encode(output.getvalue()).decode()
                        ),
                    )
                rows.append(
                    dict(
                        kind=kind,
                        status="completed",
                        result=value,
                        usage=usage,
                        elapsed_seconds=round(time.perf_counter() - began, 3),
                    )
                )
            except ProviderUnavailable as error:
                rows.append(
                    dict(
                        kind=kind,
                        status="unavailable",
                        error=str(error),
                        elapsed_seconds=round(time.perf_counter() - began, 3),
                    )
                )
    report = dict(
        recorded_at=datetime.now(UTC).isoformat(),
        model=config.ollama_model,
        threads=2,
        ollama="0.40.16",
        hardware="CPU only, x86_64 development host",
        protocol="One schema chat call then one synthetic blue garment vision call. Single attempts, no human photo. Not quality, warm/cold or throughput benchmark.",
        results=rows,
    )
    await asyncio.to_thread(
        Path("benchmarks/local-model-smoke.json").write_text, json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(report))


asyncio.run(main())
