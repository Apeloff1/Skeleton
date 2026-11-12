# Jeeves — local-only model, real offline inference, advisory multimodal

**Jeeves is the ONLY primary chat model.** OpenAI and other hosted providers
cannot answer as Jeeves or become fallback models. The application uses one
genuine, operator-owned, digest-pinned local GGUF model with the *deployment
identity* **jeeves**. This identity does not imply the underlying weights
were trained from scratch by Skeleton. Retain their real source and license.

Multimodal capabilities (images, audio, video, crawler knowledge) are
**advisory evidence**. They cannot replace the primary local text generator,
authorize tools, turn into system instructions, or trigger a hosted-model
failover. The actual model and executable, not a mock or a header alone,
must generate a verified answer before inference can be called working.

## 1. Prepare a genuine local model

Acquire a licensed GGUF and a compatible llama.cpp CLI executable and verify
their source. Neither a licensed user model nor hardware is bundled with
this change. The optional provisioner can obtain publicly pinned Qwen
weights only with an explicit --download option:

    python scripts/provision_local_ai.py --help

Use approved files already on disk to stay fully offline. Create an immutable
Jeeves deployment manifest in a directory that already exists:

    python scripts/build_jeeves_local_manifest.py \
      --model /absolute/path/to/owned-model.gguf \
      --executable /absolute/path/to/llama-cli \
      --output /absolute/path/to/jeeves.json \
      --profile qwen3-completion-chat --context 4096 --threads 2

Choose a prompt profile compatible with the actual model; raw and
llama-completion-chat are alternatives. The builder reads and hashes the
GGUF and native executable, validates the model header and runtime pins,
and creates the manifest only if absent. No external provider is contacted.

## 2. Prove real local generation

On a host that can execute the pinned native runtime:

    python scripts/install_ai_chat.py \
      --deployment /absolute/path/to/jeeves.json \
      --live-local

This invokes the actual bounded offline llama.cpp process, validates a
nonempty completion, exact model and runtime identities, and outputs a
local execution receipt digest. It never prints the answer or a key.

**This proves host-side local inference, not yet the protected application
backend or a phone.** The exact executable must be compatible with the
host; Linux container builds may not execute directly on macOS/Windows.
There is no automatic fallback to OpenAI.

## 3. Configure and start Jeeves's private application stack

Create the private env and Compose model binding:

    python scripts/install_ai_chat.py \
      --deployment /absolute/path/to/jeeves.json --apply

If replacing an existing environment, explicitly add --force to preserve
the existing valid persistent database and signing identities. Optionally
supply --admin-email and --admin-password-file to bootstrap an approved
administrator with a private password file.

Start the installed stack:

    python scripts/install_ai_chat.py \
      --deployment /absolute/path/to/jeeves.json \
      --apply --force --start

This selects AI_PROVIDER=local, JEEVES_LOCAL_ONLY=1,
JEEVES_PRIMARY_MODEL_ID=jeeves, AI_LOCAL_GUARD_REQUIRED=1, and pins one
read-only local deployment. The primary engine receives no hosted provider
key, verifier or secondary model. Docker builds may need internet access
for image/dependency acquisition, but model *inference* remains local.

A successful Compose start is only service orchestration. It does not
prove a model answer or grant authority to disable the local guard.

### Trusted protected-local admission is mandatory

A generic Compose stack cannot invent the genuine model tokenizer/sampler
attestations, independent adversarial reviewer, task-scoped canonical
snapshot reader, majority-durable Mongo writer epoch or reviewed native
bootstrap. The application composition root must bind these before the
engine is ready. Without them, report local_guard_unavailable. Never set
AI_LOCAL_GUARD_REQUIRED=0 or use the unsafe development acknowledgement
to claim a production model works. Local CLI generation is not a substitute
for the guarded product chat route.

## 4. Prove an authenticated Jeeves chat turn

Read-only account/engine/storage/model readiness:

    python scripts/ai_chat_installed_smoke.py \
      --base-url https://YOUR_BACKEND_HOST \
      --login-email owner@example.com

One real inference and durable canonical replay:

    python scripts/ai_chat_installed_smoke.py \
      --base-url https://YOUR_BACKEND_HOST \
      --login-email owner@example.com \
      --exercise --timeout 180

The exact model must have provider_id=local and model_id=jeeves. The request
explicitly pins both, even if automatic routing is nominally available.
Provider receipts must start with provider:local:. Hosted/advisory receipts,
incomplete model outputs, lost canonical assistant rows and replays that
change the answer all fail acceptance. No second POST occurs after an
uncertain network outcome.

Recover the original nonsecret IDs with GET-only requests:

    python scripts/ai_chat_installed_smoke.py \
      --base-url https://YOUR_BACKEND_HOST \
      --login-email owner@example.com \
      --recover-thread THREAD_ID --recover-request REQUEST_ID

For headless environments use --token-file with a private mode-0600 file,
never a password in command arguments. Interactive passwords require a
real terminal and are never echoed.

## 5. Android/iOS connectivity is not on-device inference

The mobile app connects to **your own authenticated backend**, not an
external AI API. To build an installed client:

    cd frontend
    EXPO_PUBLIC_BACKEND_URL=https://YOUR_BACKEND_HOST \
      npx eas build --profile apk --platform android

The local GGUF runs on the operator-owned computer/server. **The phone
is a client of that local host; it is NOT yet an independent on-device
offline model.** A disconnected phone would require a distinct native
Android/iOS inference module and real device memory/thermal qualification.
Do not equate a connected phone with locally resident phone weights.

## 6. Tests and release blockers

Focused source tests and native inference acceptance:

    python -m pytest -q --noconftest \
      tests/test_jeeves_local_policy.py \
      tests/test_install_ai_chat.py \
      tests/test_ai_chat_installed_smoke.py \
      tests/test_configure_ai_chat_hosted.py
    python -m pytest -q tests/test_app_offline_chat_cli.py
    cd frontend && node --test scripts/test-installed-chat-endpoint.cjs
    cd frontend && yarn typecheck

Real production deployment still needs an operator-owned model, actual
GGUF completion, protected engine bootstrap, canonical live chat test on
the installed app, restart recovery, hardware pressure checks, secure TLS
ingress and exact-head security/installer qualifications. This PR stays
review-only until these are proven.

| Failure | Safe response |
| --- | --- |
| No local model | Pin real licensed GGUF + llama.cpp as model_id=jeeves |
| Wrong provider or extra model | Reject; remove hosted and alternate inference routes |
| local_guard_unavailable | Install trusted snapshot/reviewer/tokenizer authorities |
| GGUF/runtime hash mismatch | Restore exact approved files and requalify |
| No local provider receipt | Reject as unverified, never substitute hosted output |
| Phone cannot reach backend | Configure own TLS ingress; never expose Mongo/engine |
