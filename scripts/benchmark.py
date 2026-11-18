"""Bounded, real HTTP catalogue benchmark. Not model-quality or load evidence."""

import argparse
import csv
import hashlib
import json
import math
import platform
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

QUESTIONS = [
    "hi",
    "what do you do",
    "classic business outfit under £100",
    "casual minimalist outfit under £70",
    "sporty workout outfit",
    "cook a recipe in this outfit",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=Path("benchmarks/catalogue"))
    args = parser.parse_args()
    rows = []
    with httpx.Client(base_url=args.url, timeout=120, headers={"Origin": args.url}) as client:
        health = client.get("/api/health").raise_for_status().json()
        if health["engine"] != "catalogue":
            raise SystemExit("This workload measures catalogue mode only.")
        for repetition in range(3):
            client.get("/api/session").raise_for_status()
            client.post("/api/clear").raise_for_status()
            for index, question in enumerate(QUESTIONS):
                began = time.perf_counter()
                result = (
                    client.post("/api/chat", json={"message": question}).raise_for_status().json()
                )
                elapsed = (time.perf_counter() - began) * 1000
                rows.append(
                    dict(
                        repetition=repetition,
                        question_id=index,
                        route=result["route"],
                        engine=result["engine"],
                        agents=" > ".join(event["agent"] for event in result["agent_trace"]),
                        reserved_output_tokens=result["token_budget"]["reserved_output_tokens"],
                        products=len(result["products"]),
                        http_ms=round(elapsed, 3),
                        server_ms=result["timings"]["total_ms"],
                    )
                )
            client.post("/api/clear").raise_for_status()
    report = dict(
        recorded_at=datetime.now(UTC).isoformat(),
        protocol="18 sequential real loopback HTTP requests; 3 six-turn conversations, no provider calls. First request is NOT process-cold-start evidence.",
        python=platform.python_version(),
        system=platform.system(),
        machine=platform.machine(),
        cpu=platform.processor(),
        model=None,
        catalogue_sha256=hashlib.sha256(Path("data/catalogue.json").read_bytes()).hexdigest(),
        health=health,
        count=len(rows),
        failures=0,
        median_http_ms=round(statistics.median(r["http_ms"] for r in rows), 3),
        p95_http_ms=sorted(r["http_ms"] for r in rows)[math.ceil(len(rows) * 0.95) - 1],
        max_http_ms=max(r["http_ms"] for r in rows),
        rows=rows,
        limits="One development host, sequential sample traffic. Not model latency, ARM, concurrent throughput, shopping accuracy or uptime evidence.",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    with args.output.with_suffix(".csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(
        json.dumps(
            {key: report[key] for key in ["count", "median_http_ms", "p95_http_ms", "max_http_ms"]}
        )
    )


if __name__ == "__main__":
    main()
