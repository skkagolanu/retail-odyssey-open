# Verification and evidence boundaries

Release verification on 2026-11-18, development host Linux x86_64, Python3.12.15 / Node24.22.3. Reports are reproducible fixtures and engineering checks, not retailer/product-quality evaluation.

| Check | Observed result | Scope |
|---|---|---|
| Backend pytest | 61 passed | SQLite sessions/races/reset/limits, strict catalogue/URL checks, HTTP security, provider failures/contracts, honest fallback, metrics |
| Ruff / mypy | Passed | All source; Ruff also tests/scripts; frontend separately strict TypeScript |
| Frontend production build | Passed | Self-contained React/CSS bundle, no frontend API keys/CDNs |
| Playwright | Four passed | Actual loopback catalogue API, two isolated contexts, reload/reset, scoped response, cards, error retry; error test deliberately intercepts503 |
| axe WCAG2A/AA/2.1A/AA tags | No violations on tested populated desktop1440px/mobile390px views | Automated test, not a complete accessibility certification |
| npm audit | Zero reported vulnerabilities | Installed locked frontend/dev dependency tree at check time |
| pip-audit | No known vulnerabilities found | Runtime requirements at check time, not proof of no vulnerabilities |
| Gitleaks release-tree scan | No leaks found | Clean release file tree; upstream history separately flagged credentials and is excluded |
| Real catalogue HTTP benchmark | 18 requests, median15.09ms, p95/max16.468ms | Sequential loopback HTTP, sample catalogue; no provider calls or cold-start/ARM/load/uptime claim |
| Real optional-model provider smoke | Recorded separately | See actual model/tag/status in `benchmarks/local-model-smoke.json`; not statistical/semantic evaluation |
| Full local-model API smoke | Recorded separately | `benchmarks/local-api-smoke.json` reports actual engine and warnings, including any fallback; never infer success from HTTP200 alone |
| Container | Passed on GitHub Actions | Actual Docker build, non-root UID10001, readiness and catalogue chat; Compose overlay configuration also validated |
| Public cloud deployment | Not deployed in this maintenance run | Render free Blueprint prepared; account connection/actual hostname still required |
| ComfyUI GPU / ARM / durable hosted metrics | Unverified | Protocol mocks only; no provisioned GPU/device/export collector |

## How the latency/failure bottlenecks were found

Original implementation inspection showed sequential remote intent, recommendation and conversation calls, blocking SDK use and timing starting after intent. The successor uses local routing, a local catalogue, optional asynchronous local inference and inclusive stage/ASGI timers. This is an architectural change, not a measured speedup against the old model stack: the old providers were not benchmarked.

The frontend audit caught an unresolved picomatch advisory through the Vite toolchain. Replacing that chain with esbuild retained strict TypeScript checking and produced a self-contained bundle; the new locked tree reports zero npm advisories. The change is a dependency reduction, not a claimed runtime speedup.

The initial real `qwen3-vl:2b` smoke completed a small schema chat in16.875s and a synthetic blue-shirt description in50.134s (two CPU threads). However, the full app's catalogue-ID request repeatedly returned an empty final answer after its350-token budget. Direct Ollama response inspection showed `done_reason:length`,350 generated tokens and a separate thinking field; `/api/show` reported thinking enabled by default. The official tag listing maps the ambiguous2b/4b tags to thinking variants. Therefore documented defaults now use explicit `qwen3-vl:4b-instruct` and the small test uses `qwen3-vl:2b-instruct`. The public app never displays reasoning traces. The follow-up real smoke report, rather than the first simpler request, determines whether the final configured pipeline succeeded.

## Reproduce

Run README checks, start the real app in catalogue mode, then `python scripts/benchmark.py`. CSV/JSON include request-level route, engine, card counts, HTTP vs server timings, catalogue hash, runtime and limits. Keep reports for other hardware/configurations under distinct names; do not overwrite an old measurement and keep its claim.

For the opt-in local model smoke: install Ollama0.40.16, pull `qwen3-vl:2b-instruct`, run `python -m scripts.local_model_smoke`. It makes two bounded requests (schema selection, synthetic garment vision) with two CPU threads and60-second provider timeout. This differs from the app default60-second per-provider budget and the default4B instruct model. No real person's image is used. Inspect `status`, not just file existence. No continuous load/thermal benchmark is performed.

Final five-agent release:57 backend tests pass, including sequential vision→recommendation→conversation handoffs, shared token budget/history trimming, independent asyncio budgets, invalid conversation-plan withholding and independent-process lease exclusion. The full real HTTP Ollama flow completed in12.088s using qwen3-vl:2b-instruct with no warnings, two selected records and separate successful recommendation/conversation calls. This is one local CPU smoke, not a latency distribution or held-out fashion quality test. The final provider smoke uses explicit2B instruct:1.408s selection and50.179s synthetic-image description; the default4B instruct remains unbenchmarked.

The optional Prometheus/Grafana overlay is provided alongside the real in-app workflow/budget meters. Local Docker/Compose execution was unavailable in the environment; Actions successfully checked the application container and Compose configuration. Remote dashboards/retention remain unverified unless a deployment is separately observed.

Implementation CI completed successfully for source `652de33`: [Checks run44292823027](https://github.com/skkagolanu/retail-odyssey-open/actions/runs/44292823027). All three jobs (`verify`, `container`, `secrets`) passed. The subsequent evidence-only commit updates this report and the controlled provider fixture; implementation code is unchanged.


Current cloud-adapter implementation: `c8438f0`. [Cloud-agent CI run44296607811](https://github.com/skkagolanu/retail-odyssey-open/actions/runs/44296607811) passed. This adds four HTTPX contract regressions for full cloud vision→recommendation→conversation→image flow, shared usage accounting, free-plan configuration, quota refusal without retry/paid fallback, and missing generated bytes. These provider responses are mocked: no live Cloudflare inference, wallet state or public deployment is established. Browser/catalogue/Docker checks remain real. See [cloud setup and acceptance checks](cloud.md). Cloud mode's512-token per-call/1536-turn reservations differ from the local128/384 policy. Secret values were neither requested in chat nor used in these tests.
