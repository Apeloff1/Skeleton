# Optional local coding profile

The existing local-model provisioner offers two explicit profiles. `chat` remains
its unchanged default: Qwen3-0.6B-Q8_0. `coding` prepares the official
Qwen2.5-Coder-1.5B-Instruct Q4_K_M model through the same canonical local runtime.
It does not start inference, switch an existing installation or approve generated
code. Actual build, repair, browser behavior and host capacity must be measured.

The coding weights are about **1.12 GB** (1.04 GiB). Provisioning reserves space
for the selected model, the bounded runtime and **two GiB left free**; allow at
least four GiB free before acquisition. The pinned runtime is Linux x86-64 glibc
CPU only. Other hosts need an explicitly prepared compatible Linux container;
preparation does not establish native compatibility.

## Prepare a separate model directory

Run from the repository with its Python environment:

```bash
python scripts/provision_local_ai.py --target linux-x86_64-glibc \
  --profile coding --context-size 12288 --download \
  --output ./data/local-ai-coding
```

Downloads require `--download` and retain proxy/CA trust and TLS verification.
Each weight transfer uses one staging inode, exact size and SHA-256 checks, then
atomic create-only publication. A partial or failed destination keeps its
`.incomplete` marker and is never activated. No weight is downloaded twice or
copied into a second full-size publication file.

When the existing chat installation has a complete matching provisioning receipt,
reuse its already verified executable and libraries:

```bash
python scripts/provision_local_ai.py --target linux-x86_64-glibc \
  --profile coding --context-size 12288 --download \
  --runtime-from ./data/local-ai --output ./data/local-ai-coding
```

`--runtime-from` verifies the source recipe, receipt, existing deployment and
all files. It copies only the pinned runtime files into the new directory and
never edits the old model, receipt or configuration. An arbitrary executable
folder is not a supported source. `--runtime-archive` remains available for an
existing exact pinned release archive; the two runtime-source flags are exclusive.
For completely offline preparation, supply `--model` with the exact pinned coding
GGUF and either runtime-source option instead of `--download`.

Selecting `coding` against an existing `chat` destination fails rather than
retargeting it. Existing context/thread/profile conflicts likewise require a fresh
directory. Keep the original directory to support an explicit later switch back.

## Activate through the existing operator configuration

Preserve the private `.env` and database volumes. Update only its existing model
selectors after provisioning reports success:

```dotenv
AI_PROVIDER=local
AI_LOCAL_MODEL_PATH=
AI_LOCAL_MODEL_CATALOG_PATH=
AI_LOCAL_DEPLOYMENT_PATH=/app/local-ai/deployment.json
SKELETON_LOCAL_MODEL_DIR=./data/local-ai-coding
```

```bash
python -m skeleton app up --production --no-build
python -m skeleton app doctor --live --studio --json
```

Confirm the authenticated model inventory identifies
`Qwen2.5-Coder-1.5B-Instruct-Q4_K_M`, then perform a bounded actual conversation or
build and inspect its runtime result and provider receipt. Readiness alone does
not prove output quality. The profile uses plain ChatML completion, without the
Qwen3 thinking-prefix tokens; fixed completion framing and exact template enter
the admitted deployment digest. The same configured operation deadlines, token,
context, admission, physical-worker and storage limits remain in force.

The two pinned chat profiles preserve system instructions, user/assistant history
and the current user prompt as separate native roles. Validated tool and JSON
schemas are visible to the model in the system frame. The runtime preserves the
exact assistant prefix through binary-file input and disables a second native
conversation wrapper. Reserved role-control tokens in message content are rejected
before dispatch. Custom/raw deployment profiles retain their existing behavior.
The corrected prompt format changes the execution-profile cache identity; existing
deployment receipts and historical results stay intact.

A coding model is not an independent reviewer by virtue of its name. Profile
selection does not fine-tune weights, authorize background research or certify a
game as playable. Generated game markup and actual browser behavior remain
separate checks.

## Pinned public identities

| Artifact | Pin |
| --- | --- |
| Official repository | [Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF](https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF) |
| Model revision | `f86cb2c1fa58255f8052cc32aeede1b7482d4361` |
| Model file | `qwen2.5-coder-1.5b-instruct-q4_k_m.gguf` |
| Exact model bytes | `1117320768` |
| Model SHA-256 | `cc324af070c2ecbfd324a30884d2f951a7ff756aba85cb811a6ec436933bb046` |
| Model license | Apache-2.0, from the official model card |
| Runtime release | Existing llama.cpp `b11429`, Ubuntu x64, MIT |
| Runtime archive SHA-256 | `f6d25dde8f51133143d1453da4fd5f73b145127177612a283bf7995957af3392` |
| Completion executable SHA-256 | `7119bef261611b26f326f7c4da4dc3fdeb7bb28e2faf1ec392bda7b21215ef52` |

The [provisioning declaration](../../machine/ai_local_model_provisioning.json)
and `scripts/provision_local_ai.py` bind these identities. The optional profile
retains the existing deployment owner and provider boundary; no extra service or
credential-bearing feature transport is introduced.
