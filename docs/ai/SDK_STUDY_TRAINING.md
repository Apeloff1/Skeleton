# SDK-wide study and Jeeves candidate training

This is a **working intake path**, not a claim that the installed Jeeves has
learned every SDK. The canonically owned implementation is
`skeleton/ai/training/sdk_study.py`, alongside existing rights-gated production
training. The SDK inventory consumes Dragon's native target catalog and the
console builder's **read-only** adapter readiness. Catalog presence, physical
installation, build success, permitted reference use and learned proficiency are
five separate states.

## Milestone 1 — inventory all declared game-target SDK surfaces

```bash
python -m scripts.training.sdk_study inventory > /private/sdk-target-census.json
```

For non-console SDKs (engine, graphics, audio, mobile, web, AI, tooling, desktop, embedded or other), add an explicit \`sdk_kind\` and \`target_ids: []\` in the source manifest. Such bundles are still verified against their exact installed documentation and receive no invented console adapter state. The census itself only claims full coverage of the **canonical console-target list**, not all third-party SDKs existing in the world.

The census reports *every* target in
`skeleton.ai.webcrawler.dragon_native_targets.target_catalog`, with native,
toolchain-adapter, licensed and historical status; declared SDK/toolchain name;
local build-adapter state and missing dependencies; plus explicit false values
for compilation, training authorization and weight updates. This census does
not visit the internet, invoke compilers, install SDKs or treat proprietary
license labels as available credentials. Operator-installed paths are normally
listed using `SKL_GAME_CONSOLE_SDK_ROOTS` by the existing console builder.
Run the command on the **actual SDK host**; the ChatGPT-connected GitHub repo
cannot enumerate files on your local workstation.

## Milestone 2 — exact pinned documentation intake

Write a UTF-8 JSON source manifest outside Git and outside public static folders:

```json
{
  "schema_version": "skeleton.jeeves.sdk_sources.v1",
  "sdks": [
    {
      "sdk_id": "rgbds",
      "version": "actual-operator-verified-version",
      "target_ids": ["game_boy"],
      "root": "/absolute/operator/installed/rgbds",
      "documents": [
        {"path": "README.md", "sha256": "sha256-of-exact-document-bytes"}
      ],
      "rights": {
        "training_permitted": false,
        "human_reviewed": false
      }
    }
  ]
}
```

Run:

```bash
python -m scripts.training.sdk_study verify-sources --sources /private/sdk-sources.json
```

For each declared document the verifier checks the actual SDK folder,
bounds, regular-file type, symlink traversal, UTF-8 for admitted training,
SHA-256 equality, and allowed textual extensions. Nothing is downloaded or
executed. A missing document, digest change or invalid path stops the run.

An operator may mark a document *candidate training eligible* only after
independent verification of applicable terms and explicit human authorization:
`training_permitted: true`, `human_reviewed: true`, and actual
`rights_holder`, `rights_basis` beginning `license:`, `original:` or
`public-domain:`, and `review_id`. These declarations are custody records,
**not** automatic legal proof. Proprietary, restricted SDKs should remain
inventory-only without an express training grant. Do not add credentials,
private keys, firmware, commercial ROMs or restricted source.

## Milestone 3 — add reviewed question/answer pairs to Jeeves

Prepare private UTF-8 JSONL, one row per *human-authored and checked*
question/answer. Rows refer to exact pinned documents from the source manifest:

```json
{"schema_version":"skeleton.jeeves.sdk_reviewed_example.v1","id":"sdk.rgbds.example01","sdk_id":"rgbds","source_sha256":"sha256-of-exact-document-bytes","split":"train","module_id":"jeeves.coding.types.construct","prompt":"Explain how to declare an original sprite's tile metadata using this SDK.","answer":"A detailed independently checked answer grounded in the pinned SDK version, with a reproducible original example.","quality_approved":true,"quality_reviewer_id":"named-human-reviewer","quality_review_note":"Checked against versioned installed documentation and verified an original project."}
```

Use registered `jeeves.coding.*` or `jeeves.gaming.*` module identifiers from
`machine/jeeves_training_modules.json`. Each SDK is one source project and must
stay entirely in either training or held-out; do not split a single SDK's
documentation between both. An existing independently approved multidomain
corpus is REQUIRED, because the production trainer also verifies minimum
coverage of gaming, AI, and coding, and independent project counts for
training and held-out evaluation.

```bash
mkdir -p /private/sdk-corpus-v2
python -m scripts.training.sdk_study extend-corpus \
  --sources /private/sdk-sources.json \
  --reviewed /private/sdk-checked.jsonl \
  --base-manifest /private/approved-multidomain/manifest.json \
  --output-dir /private/sdk-corpus-v2 \
  --prefix sdk_revision_002 \
  --review-id signed-human-sdk-review-002
```

The extension checks the entire original corpus, verifies each SDK example's
source SHA and rights, checks project-level split separation, near-duplicate
contamination and registered modules, stages a new pair of JSONL files,
validates the **complete** resulting corpus with the production
`load_multidomain_corpus` path, then publishes files exclusively with the
manifest **last**. Existing files, base corpus, serving checkpoint and
candidate checkpoints are never overwritten. The new manifest records the
base, source and reviewed-intake hashes. It is the input to the existing
production candidate-training flow.

## Milestone 4 — actually train, evaluate, then consider promotion

Use the existing `docs/ai/JEEVES_PRODUCTION_GAME_TRAINING_RUNBOOK.md`.
It requires the operator's compiled app, a restored **actual speaking**
Jeeves checkpoint, an in-process attestation, a separate candidate copy, a
verified output directory, approved data, disk/time admission and independent
held-out evaluation. Pass the new `*-manifest.json` as the dataset manifest.

A successful SDK corpus publication is **not** weight training. Do not claim
SDK mastery until checkpoint-derived candidate training, per-SDK build/synthesis
evaluation, independent quality review and explicit promotion succeed.
Track per-SDK readiness and improvement separately, including errors,
unsupported APIs, interface/compiler diagnostics, reproducible examples,
resource ceilings and rollback. Proprietary SDK access remains an external
prerequisite; the system must neither bypass terms nor fabricate SDK coverage.
