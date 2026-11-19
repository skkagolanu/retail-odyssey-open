# Retail Odyssey Open

A local-first **multi-agent fashion assistant** with sequential context handoffs, grounded model generation, shared token budgets and per-agent observability. Product cards remain catalogue-backed; browser conversations are isolated. Runs on **Python 3.12** and **Node 24**. MIT licensed.

**Public app:** [retail-odyssey-open.onrender.com](https://retail-odyssey-open.onrender.com). Render Free deployment and four public browser checks are verified. It currently runs catalogue mode; actual cloud-agent inference remains pending private Cloudflare configuration.

This is an independently maintained derivative of [Retail Odyssey](https://github.com/skkagolanu/Retail-Odyssey), starting from `c272839a51bc0cc8104b4a2ef649ca36b2e49774`. It has clean release history; the original project is unchanged. See [NOTICE](NOTICE).

## Agent pipeline

`IntentAgent → VisionAgent (image only) → RecommendationAgent → ConversationAgent → ImageGenAgent (visualization only)`

Each agent has its own contract and prompts. The orchestrator passes immutable turn context in sequence: intent/preferences → wardrobe observations → catalogue candidates/selected IDs → constrained styling plan → optional image prompt. Greetings and out-of-scope turns use a local response. Catalogue mode is the provider-free baseline; Ollama mode invokes separate recommendation and conversation model calls, plus vision when an image is supplied.

A shared per-turn budget reserves at most **384 output tokens locally (1,536 in cloud mode)** across model agents, **128 per local call / 512 per cloud call**, with a **4,096-token context window** and conservative input estimation/history trimming. Model output must validate before it reaches the next agent. Product IDs are restricted to retrieved candidates; the conversation agent generates enum-constrained styling/follow-up plans rendered with server-owned facts. This provides constrained generation without allowing invented product fields.

Inspect the in-app **Behind the reply** view for invocation order, handoffs, stage timings and token reservations vs actual usage. Correlated JSON logs and Prometheus metrics support an optional, containerized read-only Grafana dashboard. [Agent architecture](docs/architecture.md).

## What works without an API key

- Ask for a casual, business, formal, wedding, party or workout outfit; add a style and an outfit-total budget in GBP.
- Browse typed product cards with recorded prices and source provenance. The included **12 fictional sample pieces** have illustrative prices and **no purchase links**. They are not real stock or Frasers listings.
- Follow up using retained preferences, clear the entire conversation, or reload within the session lifetime.
- View schematic garment moodboards, server-stage timing and Prometheus metrics.

Cloud mode uses Render Free + Cloudflare Workers Free for the actual text/vision/image agents. [Cloud deployment](docs/cloud.md) describes setup and hard free-plan limits. Optional local Ollama adds structured catalogue selection, a separate conversation-agent styling plan, and wardrobe-image descriptions. Optional self-hosted ComfyUI adds generated illustrations. Neither service is silently replaced by paid inference. No Gemini, OpenAI, Hugging Face SDK or hosted inference service is required. Hardware, electricity and any hosting still cost resources; this is not a promise of free GPU hosting.

## Run locally

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
npm --prefix frontend ci
npm --prefix frontend run build
uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Open **http://127.0.0.1:8000**. No `.env` is needed for catalogue mode. Optional settings are in [.env.example](.env.example); all environment names begin with `RO_`. The application serves its own built frontend. For frontend changes, rebuild or run `npm --prefix frontend run watch` and reload the page.

With Docker:

```bash
docker compose up --build -d
```

The single app port is bound to loopback; session data uses a named SQLite volume. For a public deployment, configure your exact HTTPS origin and trusted hostname, enable secure cookies, terminate TLS, and protect `/metrics` at the proxy. See [operations](docs/operations.md).

## Free cloud deployment with model agents

The primary [Render Blueprint](render.yaml) now selects the **real cloud-agent path**: Render Free hosts the application; Cloudflare Workers Free supplies text/vision inference and requested generated images. No local model server is required. [Cloud setup](docs/cloud.md) covers private configuration, account connection, free-plan verification and public end-to-end acceptance checks.

Stay on Workers Free and Render Free. Inference stops at the free allowance; this is quota-limited rather than unlimited/always-on. Render sleeps when idle and its ephemeral storage resets conversations. The app does not upgrade plans or switch to a paid provider. Operator free-plan confirmation is required and is not an independent billing audit. Live cloud completion is only claimed after observing the actual deployment.

The separate [catalogue-only Blueprint](render.catalogue.yaml) is a model-free baseline. It is not the requested cloud multi-agent demonstration.

## Optional local AI

Install [Ollama](https://docs.ollama.com/quickstart), then:

```bash
ollama pull qwen3-vl:4b-instruct
RO_ENGINE=ollama RO_OLLAMA_MODEL=qwen3-vl:4b-instruct uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Ollama must be reachable on the configured local URL. `qwen3-vl:2b-instruct` is a smaller option for limited hardware; the recorded CPU smoke test uses that model, not the default 4B. Check the model's licence before redistribution. Qwen3-VL weights use Apache 2.0. No weights are bundled here.

Compose users can start the `models` profile, pull the model, then restart the app with Ollama enabled:

```bash
docker compose --profile models up -d ollama
docker compose exec ollama ollama pull qwen3-vl:4b-instruct
RO_ENGINE=ollama docker compose --profile models up --build -d app
```

Recommendation-agent output selects only supplied catalogue IDs. The conversation agent generates a separate schema-constrained styling/follow-up plan. Displayed product facts and commerce prose are server-owned; arbitrary generated prose is not displayed. Failed, invalid or truncated output uses the **same catalogue** with an explicit warning. Vision descriptions can be wrong and are used only as untrusted search hints. Images are optional and never analysed in catalogue mode.

For generated illustrations, configure your own ComfyUI API-format workflow as described in [providers](docs/providers.md). Missing or failed generation is reported as unavailable. The default SVG moodboard is always labelled schematic.

## Checks and evidence

```bash
ruff check src tests scripts
ruff format --check src tests scripts
mypy src
pytest -q
npm --prefix frontend run format:check
npm --prefix frontend run build
cd frontend && npx playwright install chromium && npm run test:e2e
# With the app already running in catalogue mode, from repository root:
python scripts/benchmark.py --output benchmarks/catalogue
```

Browser tests use the actual catalogue API; provider protocol tests use HTTPX mocks and are labelled accordingly. [Verification](docs/verification.md) distinguishes measured results from unverified capabilities. [Limitation fixes](docs/limitations.md) maps the original audit to implementation and tests. [Architecture](docs/architecture.md) covers state and trust boundaries.

## Provenance

The original three-person team project won **[Hackathons UK] Best Use of AI Agents on Arm** at HackSheffield10, **29–30 November 2025** ([project record](https://devpost.com/software/retail-odyssey), [organiser](https://hacksheffield10.devpost.com/)). That award belongs to the original submission, not this derivative. It does not establish sole authorship, ARM performance, production uptime or this version's capabilities. This maintenance is AI-assisted; see NOTICE for attribution.
