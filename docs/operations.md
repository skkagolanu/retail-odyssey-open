# Operations

Default run: Python3.12, built frontend, persistent writable `var/`, catalogue mode. Bind loopback during development. No database, inference or browser key service is required. Docker Compose uses a non-root app and a named session volume. No ARM optimization claim is made; architecture-capable base images are not an ARM benchmark.

For public hosting:

1. Put a maintained TLS reverse proxy before the API. Forward only trusted host headers and set `RO_ALLOWED_ORIGINS='["https://your.example"]'`, `RO_TRUSTED_HOSTS='["your.example","localhost"]'`, `RO_SECURE_COOKIES=true`. Match the public origin exactly. Keep localhost in trusted hosts for container readiness.
2. Persist `/app/var` on a local durable filesystem; SQLite WAL is not intended for separate machines on shared network storage. Back up according to your own retention policy. Clearing removes current session fields, not backups or filesystem forensic copies.
3. Apply proxy/global request and session-creation limits. In-app defaults bound sessions, per-session chat rate, history, uploads, model output and parallel replies. They do not prevent distributed anonymous abuse. Keep providers on a private network. Restrict `/metrics`; do not publicly expose Ollama/ComfyUI.
4. Probe `/api/health`: inspect JSON `status`, not only HTTP200. `ready` means catalogue loaded and configured inference available; `degraded` means optional inference unavailable. Container health checks enforce that distinction. Readiness does not prove future uptime or semantic quality.
5. Scrape `/metrics` with your own Prometheus. Names are defined in `src/utils/prometheus_metrics.py`; create dashboards against those names. The old misleading session/currency counters and bundled default-admin dashboard configuration were removed. Scrape each process separately; for this SQLite demo, prefer one API worker.
6. Inspect sanitized server errors, provider failure counters and stage histograms. Access logs are disabled in the documented start commands. This app has no external trace collector or guaranteed durable metric retention; configure these operational services separately if needed. Benchmark measured traffic before making latency claims.

Optional local model CPU inference can take tens of seconds. Catalogue mode remains a fast useful baseline, but its results are deterministic sample matching. There is no generic free-tier GPU uptime guarantee. Model startup, image generation, real inventory integrations and human fashion relevance need separate measurements.

Refresh dependencies deliberately: regenerate constraints on Python3.12, run backend checks, npm audit/build and browser tests, then container CI. Avoid publishing old history or real customer/image data. For deployment failures, first check health mode/model tags, filesystem permissions, exact origin/host settings and proxy body/time budgets.

## Free public Render demo

[Render free web services](https://render.com/docs/free) support this Docker app. Use this repository's [render.yaml](../render.yaml) through **New → Blueprint**, or create a Docker web service from the repository and explicitly select **Free**. No model/API key is needed. This config does not provision paid services, a database or a disk.

Once Render assigns your actual HTTPS hostname, set these dashboard environment variables, then deploy/redeploy:

```text
RO_ALLOWED_ORIGINS=["https://YOUR-ACTUAL-NAME.onrender.com"]
RO_TRUSTED_HOSTS=["YOUR-ACTUAL-NAME.onrender.com","localhost"]
```

The Blueprint prompts for these values instead of guessing an available name or disabling host checks. Use the actual assigned URL, not the example above. The app listens on port8000, which Render Docker web services can detect. Keep a single instance. Run the browser regression against the assigned URL with `RETAIL_BASE_URL=https://YOUR-ACTUAL-NAME.onrender.com npm --prefix frontend run test:e2e` after deployment.

Render currently spins free web services down after 15 idle minutes; wake-up takes about one minute. Runtime filesystem changes are lost on spin-down, restart or deploy. Therefore the bundled catalogue/code survive, but conversations reset. The default persistent SQLite design requires durable storage when persistence is needed; this free hosting configuration does not provide it. Free instance hours/bandwidth/build allowances also apply. Do not claim always-on uptime or durable session retention on this plan. No keep-alive workaround is configured. The optional CPU/GPU model services are not included in this Blueprint.

Source/config reference: [Render free limitations](https://render.com/docs/free), [Blueprint specification](https://render.com/docs/blueprint-spec). Hosting infrastructure is managed by Render; the application code remains open source. This configuration is deployable preparation, not evidence that a Render account/service is already deployed.


## Agent monitoring dashboard

```bash
docker compose -f docker-compose.yml -f compose.monitoring.yml up --build -d
```

Open http://127.0.0.1:3000 for the provisioned **Retail Odyssey Open - Agent pipeline** dashboard; Prometheus is on loopback9090. This local dashboard is anonymous Viewer-only with initial admin creation and login disabled; there is no baked-in admin credential. Do not expose it directly to the internet. The Prometheus named volume preserves scraped samples across container replacement; default Prometheus retention applies. This configuration does not verify hosted retention. View generated metrics against actual agent requests, and distinguish reserved budgets from reported usage. New counters start afresh on app restart.
