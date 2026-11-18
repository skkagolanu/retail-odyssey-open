# Cloud-hosted multi-agent setup

This path runs the actual model agents without a local PC or rented GPU:

- **Render Free** hosts the existing FastAPI API, React UI, orchestration and session store.
- **Cloudflare Workers AI on Workers Free** serves `@cf/qwen/qwen3.8-27b` for separate recommendation, conversation and optional vision calls, and `@cf/black-forest-labs/flux-1-schnell` for requested outfit images.
- The original sequence, immutable handoffs, schemas, selected-ID constraints, shared token budgets, stage metrics and sanitized correlation logs remain intact. Cloud reasoning calls reserve at most512 output tokens each/1536 per turn (versus128/384 locally), with low reasoning effort and a4096 context limit. These are upper reservations, not claims of actual consumption. No Ollama or ComfyUI service is needed in this mode. Local mode remains available separately.

The application is open source. Render/Cloudflare hosting are managed services, not open-source infrastructure promises. Cloudflare model licensing is independent of the repository MIT licence.

## Wallet boundary

Select **Free** for the Render service and **Workers Free** in the Cloudflare account. Cloudflare currently includes10,000 neurons/day; Workers Free refuses further inference when its allowance is exhausted. It does not automatically become Workers Paid. Render also has free-hour/bandwidth/build allowances and can suspend services at limits. Do not upgrade Workers to Paid, enable prepaid AI Gateway credits or provision paid Render resources for this demo.

The app requires `RO_CLOUDFLARE_FREE_PLAN_CONFIRMED=true` before cloud mode starts. This is an operator confirmation, not an API-verification of billing state. The app cannot guarantee zero account charges if you enable paid plans or use other paid services. It does not create billing subscriptions, auto-upgrade or switch inference providers. Quota failures produce explicit unavailable/fallback states, with no hidden retry. Text token reservations do not measure image GPU neurons; the provider's Free-plan limit is the billing boundary.

Current sources: [Cloudflare Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/), [Render free limitations](https://render.com/docs/free).

## Connect and configure

1. Connect the Render integration to the account/workspace where the service should live, or create a **Free Docker web service** from this public GitHub repository. The primary [render.yaml](../render.yaml) is the real cloud-agent Blueprint; [render.catalogue.yaml](../render.catalogue.yaml) is the explicitly separate model-free baseline.
2. In Cloudflare, verify the account is using **Workers Free**. Copy the account ID. Create an account-scoped API token for Workers AI inference and model discovery. Use Cloudflare's Workers AI token guidance; do not grant global account administration. Keep its value private.
3. In the Render service's private **Environment** settings, set:

```text
RO_ENGINE=cloudflare
RO_CLOUDFLARE_ACCOUNT_ID=<account ID>
RO_CLOUDFLARE_API_TOKEN=<private token>
RO_CLOUDFLARE_FREE_PLAN_CONFIRMED=true
RO_ALLOWED_ORIGINS=["https://ACTUAL-SERVICE.onrender.com"]
RO_TRUSTED_HOSTS=["ACTUAL-SERVICE.onrender.com","localhost"]
RO_SECURE_COOKIES=true
RO_MAX_INFLIGHT=1
RO_MAX_SESSION_REQUESTS_PER_MINUTE=6
```

Use the **actual assigned hostname**. Never put the token in frontend variables, source files, logs, screenshots or chat. The Blueprint prompts for the account, token, free-plan confirmation and host values instead of inventing them. Startup refuses incomplete cloud configuration. Health discovers the exact configured cloud model without making a billable generation call.

4. Deploy/redeploy. `/api/health` must report `engine:cloudflare`, `status:ready`, the configured model and `image_generation_configured:true`. This checks access/model discovery, not inference quality. A200 with `degraded` is not success.
5. Run real public regression: greeting → purpose → business outfit → colour/cheaper follow-up → off-topic request → uploaded synthetic shirt → requested outfit visualization. Confirm `engine:cloudflare`, actual successful model stages, no unavailable warnings on expected-success requests, valid catalogue cards, returned image bytes, usage and trace correlation. Test a separate browser session and full clear. Record statuses/latencies from that actual deployment; mocked contracts are not hosted evidence.

## Capability and operating limits

The bundled catalogue is still explicitly fictional; cloud inference does not create real merchant inventory. Cloud model prose stays schema-constrained and product facts stay server-owned. Only validated data images are sent to the vision model; arbitrary remote URLs are never fetched. Generated image bytes must decode and pass the same image limits before success is reported.

Render Free sleeps after15 idle minutes and can take about a minute to wake. Its local filesystem is ephemeral, so SQLite conversations reset on restart/deploy/sleep. This is a free public demo, not an always-on/durable hosted service. Runtime requests/wardrobe images now leave the application server for Cloudflare inference; review the provider's data policies before uploading personal images. GPU image generation latency and quota capacity require actual hosted measurement.

Cloud provider implementation and61 backend regressions, including mocked five-agent cloud handoff and quota paths, can be verified without credentials. **Public cloud deployment and real Cloudflare generation remain unverified until account connection/configuration and live regression succeed.** Previous local Ollama measurements do not establish this new path's latency or quality.
