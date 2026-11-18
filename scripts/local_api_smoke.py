"""Opt-in one-request real local-model API smoke; start an Ollama-mode app first."""

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8001")
    parser.add_argument("--output", type=Path, default=Path("benchmarks/local-api-smoke.json"))
    args = parser.parse_args()
    if urlsplit(args.url).hostname not in {"127.0.0.1", "localhost"}:
        raise SystemExit("This opt-in fixture is for a local service only.")
    with httpx.Client(
        base_url=args.url, headers={"Origin": args.url}, timeout=100, trust_env=False
    ) as client:
        health = client.get("/api/health").raise_for_status().json()
        if health["engine"] != "ollama":
            raise SystemExit("Start the app in Ollama mode for this smoke.")
        client.get("/api/session").raise_for_status()
        client.post("/api/clear").raise_for_status()
        start = time.perf_counter()
        result = (
            client.post("/api/chat", json={"message": "A classic business outfit under £100"})
            .raise_for_status()
            .json()
        )
        record = dict(
            recorded_at=datetime.now(UTC).isoformat(),
            protocol="One real loopback HTTP catalogue/Ollama chat, no mocks. Warm-model state is uncontrolled; not a cold/warm, quality or throughput benchmark.",
            health=health,
            http_ms=round((time.perf_counter() - start) * 1000, 3),
            result=result,
        )
        client.post("/api/clear").raise_for_status()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2) + "\n")
    print(
        json.dumps(
            dict(
                http_ms=record["http_ms"],
                engine=result["engine"],
                warnings=result["warnings"],
                cards=len(result["products"]),
            )
        )
    )
    if result["engine"] != "ollama" or not result["products"]:
        raise SystemExit(
            "Model selection did not complete; fallback remains in the evidence report."
        )


if __name__ == "__main__":
    main()
