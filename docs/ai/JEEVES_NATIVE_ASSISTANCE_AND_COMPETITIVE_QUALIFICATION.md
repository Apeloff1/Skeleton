# Jeeves native assistance and competitive qualification

This candidate stacks on the existing Jeeves deliberation and transformer-memory source. It adds explicit local operations to the existing authenticated browser and primary chat server. It does not replace the Jeeves model or silently add any generated text to chat, memory, or the reference library.

## Native auxiliary model configuration

The optional media and independent-review peers require trusted, locally installed compatible llama-server builds and GGUF artifacts. A media model additionally requires its matching multimodal projector, and its actual capabilities must be confirmed by live testing. The separate reviewer requires a different model artifact SHA-256 from the primary Jeeves model. Distinct bytes alone do not establish distinct training lineage or statistical independence.

The adapter uses an owner-only Unix socket directory, an ephemeral API key, fixed CPU-only launch arguments, bounded input and output, process-group cleanup, deadline monitoring, exact asset hashing, and conservative observed host-memory admission. It does not enable remote endpoints, downloads, arbitrary flags, agent tools, or shell execution. This does not provide a hard kernel memory cap, a native decoder sandbox, or independent hardware attestation. POSIX Unix-socket execution is required; Windows remains held. Use trusted, owner-controlled artifact directories. Dynamically loaded native libraries and model/runtime compatibility need independent qualification.

Manifest shape (replace the example paths and every digest with independently checked local artifact identities):

    {
      "schema": "skeleton.jeeves.native-peer.v1",
      "binary": {"path": "/opt/jeeves/llama-server", "sha256": "<64 lowercase hex>"},
      "model": {"path": "/opt/jeeves/vision.gguf", "sha256": "<64 lowercase hex>"},
      "projector": {"path": "/opt/jeeves/mmproj.gguf", "sha256": "<64 lowercase hex>"},
      "modalities": ["text", "image"],
      "context_tokens": 8192,
      "max_output_tokens": 1024,
      "threads": 4,
      "timeout_seconds": 300
    }

For a text-only reviewer use a separate model manifest with projector null, modalities ["text"], and a distinct model artifact hash. The manifest is also pinned by its own SHA-256. Configure the existing offline HTTP service with its normal primary checkpoint/deployment, database and token-file flags, plus:

    --media-peer-manifest /opt/jeeves/media.json
    --media-peer-manifest-sha256 MEDIA_MANIFEST_SHA
    --reviewer-peer-manifest /opt/jeeves/reviewer.json
    --reviewer-peer-manifest-sha256 REVIEWER_MANIFEST_SHA

The native media panel accepts PNG/JPEG/WebP decoded to bounded JPEG pixels, PCM16 mono/stereo WAV, or bounded MP4 decoded to 1–6 chronological timestamped visual samples. Pillow and PyAV are optional local dependencies. Actual audio inference is dependent on the pinned server build and model; unsupported input is rejected. MP4 is sampled visual reasoning, not full video-encoder or audio-track processing. Inputs are limited to 4 MiB and raw media is not intentionally persisted by the adapter. Native libraries, OS swap and crash dumps are outside this claim. Results are unverified model observations. Export or incorporate the reviewed observation into a visible draft explicitly.

## Abstractive dialogue compression

Choose the exact saved history prefix, chunk byte limit, map/final token limits and deadline. The preview enumerates source offsets and hashes and rejects an over-budget plan. Execution rechecks the plan and submits every selected historical dialogue span to actual primary-model map calls, followed by four-way hierarchical reduction and a final abstraction. The primary transcript remains unchanged. Intermediate texts are transient; the result records input/output and execution receipt hashes, source lineage, counts and final summary. A generated summary can omit or misinterpret information even when every source byte was supplied. Review it before explicit draft reuse. There is no hidden context replacement, automatic memory write, or general semantic-faithfulness certification. Selected prefixes exceeding the bounded operation must be split manually. At most 64 chunks, 256 KiB selected source, 96 calls and a 1536-byte final summary are supported per operation.

## Independent reasoning checks

Open the existing review dialog on an exact saved locally executed answer, inspect the configured reviewer, and explicitly approve a separate native model review. It receives the exact question, displayed answer, full bounded preceding dialogue, and historical grounding passages when applicable. Oversized context is rejected rather than silently trimmed. It must return a closed JSON judgment with exact answer quotes. Supported deterministic predicates include exact, contains, excludes, strict-json and rational-span. The latter recomputes a bounded rational expression using a closed AST interpreter, then compares it with a specified answer character span. Example:

    [{"kind":"rational-span","expression":"(1 + 2) / 3","start":0,"end":1}]

The predicate is supplied by the reviewer/operator; it is not an automatically inferred ground-truth answer. A failed predicate dominates favorable model feedback. Neither a model judgment nor a local execution receipt establishes external factual truth. No automatic answer rewrite or tool action is performed.

## Actual competitive qualification

Run two explicitly configured local model services in separate private test databases. Supply distinct exact model artifact identities and identical case inventory/protocol. The competitive CLI supports actual live execution, rather than scoring invented answers:

    python -m skeleton.app.jeeves_competitive_qualification \
      --execute --left-port LEFT_PORT --right-port RIGHT_PORT \
      --left-token LEFT_PRIVATE_TOKEN_FILE --right-token RIGHT_PRIVATE_TOKEN_FILE \
      --left-model-digest LEFT_MODEL_SHA --right-model-digest RIGHT_MODEL_SHA \
      --left-db LEFT_PRIVATE_SQLITE --right-db RIGHT_PRIVATE_SQLITE \
      --left-capture left.json --right-capture right.json \
      --output comparison.json --output-tokens 512 \
      --generated-count 100 --seed 2026 \
      --blind-package review.json --blind-map private-review-map.json

The same command without --execute audits existing complete captures. The case inventory settings must exactly match the original captures. Use disjoint shards of at most 4,000 turns. The runner does not download weights or invent results. It captures actual answers, prompt/output counts and request wall-clock latency, scores the same deterministic criteria, reopens each database read-only to validate transcript/request/model/tokenizer/output/receipt custody, and reports paired case-level exact statistics. It can produce randomized blind human review materials with a separately retained mapping, not fabricated human judgments. Protect these private output files. Generated variants are not necessarily statistically independent. Timing is not hardware-equivalent unless device and thermal conditions are independently established. Local database agreement is not independent physical inference attestation. No promotional decision or general competitive-superiority claim follows automatically.

## Qualification and holds

Run the focused tests after assembling the candidate:

    python -m unittest skeleton.testing.test_jeeves_native_assistance skeleton.testing.test_jeeves_competitive_qualification
    python -m unittest skeleton.testing.test_jeeves_deliberation skeleton.testing.test_jeeves_transformer_memory
    python -m compileall -q skeleton/app/jeeves_native_peer.py skeleton/app/jeeves_native_multimodal.py skeleton/app/jeeves_semantic_compression.py skeleton/app/jeeves_independent_verification.py skeleton/app/jeeves_competitive_qualification.py skeleton/app/offline_http.py skeleton/app/offline_web.py

Synthetic test fixtures and decoded PCM/image fixtures do not establish pretrained model quality. Actual pretrained multimodal and verifier assets, real device runs, external/human semantic judgments, exact-head UI and CI qualification, native decoder/runtime security review, and paired benchmark captures remain required. No merge, release, or SOTA claim is authorized by this implementation.
