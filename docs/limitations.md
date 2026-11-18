# Original audit → successor fixes

Scope: source `skkagolanu/Retail-Odyssey@c272839` versus this independent derivative. The original repository remains unchanged. Fixes below concern implementation, not invented business outcomes.

| Original finding | Successor implementation | Evidence |
|---|---|---|
| Global conversation shared across users (C01/C07) | Random browser cookies, hashed identifiers, separate SQLite state, cross-worker leases | `tests/test_sessions.py`: browser isolation, persistence, cross-worker ownership |
| Unbounded retained messages; clear retains preferences/state (C07) | Bounded complete exchanges, TTL/capacity; clear replaces every field and invalidates in-flight replies | bounded-history, complete-reset and stale-reply tests |
| Substring retailer checks / path spoofing (C03) | Typed source records; parsed HTTPS hostname allowlist, no userinfo or alternate ports | `tests/test_grounding.py`: 11 spoofing variants + canonical source |
| Ungrounded/unconstrained fallback and no-key fictional success (C09) | Same validated catalogue for normal/fallback paths; displayed facts/prose server-owned; no model-generated shop fields | invalid-ID/price fallback, no-provider image tests |
| Frontend invents default retailer from prose (C09) | Structured cards preserve record brand/retailer/timestamp; fictional samples have no checkout URL | real API browser card/source checks |
| Fake wardrobe findings/generated image success | No image analysis in catalogue mode; image only successful after actual byte validation | provider/image tests; explicit browser unavailable state |
| Paid/legacy provider and browser key dependency | No Google/OpenAI/HF runtime packages; optional local Ollama and separate ComfyUI; self-bundled React/CSS | exact requirements and npm lockfile; production build/no-key API |
| Synchronous calls block API | Async bounded provider I/O and thread-offloaded SQLite/image processing; global backpressure | timeout/lease release and health-during-backpressure tests |
| Metrics count clearing as users and currency as products (C02/C08) | Separate created/active/reset counters; actual typed-card counts; full ASGI + stage timers including intent | literal metric/timing regression |
| Unsupported 2.5–10s and ARM optimization (C04) | Claims removed; small real HTTP catalogue benchmark with raw CSV/JSON, exact limitations | `benchmarks/catalogue.*`; no ARM comparison claimed |
| Inconsistent event dates (C05) | Single sourced event date 29–30 Nov2025; original award separated from derivative | README/NOTICE, original Devpost + organiser |
| No execution evidence | Backend contracts, real catalogue browser regression, accessibility checks, model smoke, CI/container checks | verification report distinguishes mock/live paths |
| Arbitrary remote image fetch / unbounded image input | No URL images; strict data-image types, dimensions/bytes/re-encoding/body budget | malformed-image, request-body/chunk tests |
| Wildcard credential CORS / reset race | Exact configured origins/hosts, SameSite HttpOnly cookies, POST Origin checks, CAS reset | CSRF/host, race and browser isolation tests |
| Potential secrets in original Git history | Clean release root, licence/attribution retained, original history not pushed | release-tree/history secret scanning; upstream key rotation is owner work |

## Deliberate capability boundaries

- Included sample items are fictional. No live stock, retailer affiliation, purchase/cart integration or current-price guarantee is offered. Import permitted retailer snapshots for real records; snapshots still require refresh and source-quality review.
- Model-guided selection and wardrobe descriptions are optional. Valid schema does not prove description accuracy; no human-labelled fashion/vision evaluation is claimed. Free-form model prose is not public answer content.
- Default visuals are schematic. Real ComfyUI inference requires a valid workflow, weights and hardware; protocol mocks do not prove real generated output.
- Session cookies are bearer identifiers, not account authentication. Storage/backups and local providers need an operator-defined privacy/retention policy. No hosted uptime, external telemetry retention, concurrent capacity or ARM performance is claimed.
- The original team's award is not a benchmark or a derivative award. AI-assisted maintenance must not become a sole-authorship claim.

Core multi-agent behavior is retained through five agent modules, explicit sequential handoffs, grounded schemas, shared token budgets, conditional invoking, correlated sanitized logs, per-agent tests/profiling, in-app workflow visualization and optional Prometheus/Grafana containers. Catalogue-only operation is a measured provider-free baseline, not evidence that model agents ran.
