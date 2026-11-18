# Local provider contracts

Ollama uses asynchronous HTTPX against `RO_OLLAMA_URL` (default loopback:11434), no API key, no redirects or ambient proxy routing. POST `/api/chat` sends `stream:false`, a Pydantic JSON schema in `format`, temperature zero, shared per-turn context/output budgets and two CPU threads. POSTed image data is normalized base64 in the user message's `images` array. Responses must finish (`done:true`) and validate against the schema. Counts/durations are recorded only when actually reported. GET `/api/tags` checks the exact configured model for readiness. Health reports degraded when the optional model is unavailable; catalogue fallback remains available.

Reference: [structured outputs](https://docs.ollama.com/capabilities/structured-outputs), [vision](https://docs.ollama.com/capabilities/vision). Local generation is separate from Ollama's cloud service. Model download and update checks may use the internet; run with `OLLAMA_NO_CLOUD=1` and network controls for offline inference after downloading weights.

For ComfyUI, export a working workflow **in API format**, keep it outside web-served paths, and set:

```text
RO_COMFYUI_URL=http://127.0.0.1:8188
RO_COMFYUI_WORKFLOW=/absolute/path/to/workflow-api.json
```

Replace the positive prompt input's whole string with `{{prompt}}` and any seed input's whole value with `{{seed}}`. This workflow is administrator-controlled, never uploaded by a chat user. The adapter POSTs `/prompt`, polls `/history/{prompt_id}`, fetches `/view` only for a safe output filename, validates/re-encodes actual image bytes, and removes only its own queued job. It does not install custom nodes or model weights. Use a locally licensed generation model suitable for your hardware; verify each weight's licence separately. ComfyUI itself is GPL-3.0 and remains a separate service; model licences are independent.

Reference: [ComfyUI server routes](https://docs.comfy.org/development/comfyui-server/comms_routes). Protocol tests do not establish successful real GPU image generation. No successful generation is claimed until a real configured workflow produces validated image bytes.

The conversation agent invokes a separate schema for styling/follow-up codes. All model agents share a turn budget through ContextVar. Default provider timeout is60seconds, whole-turn timeout90seconds; image generation and vision can exhaust those budgets on CPU. Truncated (`done_reason:length`) and invalid outputs are unavailable, never accepted as completed answers.
