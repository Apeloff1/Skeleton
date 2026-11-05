# Offline cognition and operational AI capability fabric

This package is a source-controlled architecture for offline AI retrieval,
memory, context management, planning, admissions, tools-as-inert-proposals,
real GGUF supervisor receipt consumption, deterministic evaluation and
auditable restart. Its shared Python core contains finite algorithms and
scope checks. Sixty-four operator-domain capability packages bind these
primitive operations to the selected resource and provenance contracts.

The authoritative model execution remains the existing
`SupervisedAI`/`ExecutionSpine` with installed GGUF digest validation,
private SQLite state, owner authentication and source-bound receipts.
Nothing here invents generated text or permits an unverified model to
modify files or call network providers. A signed operator token or model
rights proof must originate outside the LLM.

```bash
python -m skeleton.ai.runtime.operational_ai.offline_cognition.cli
python -m unittest discover -s skeleton/testing -p 'test_offline_cognition_*.py' -q
```

The source casebooks hold 64 x 40 immutable profile scenarios, including
38 fail-closed adversarial mutations per domain. These are schema/provenance
regressions, **not** real native-model or hardware qualification.

Real laptop tests, third-party checkpoint rights, Windows/WSL2 installation,
cold restart, exact-head Merge Readiness/Backend Quality/App E2E/security,
independent review, workload latency and privacy/consent review are separate
required release holds. No skipped or missing gate is success.

## Actual signed source-grounded AI work

The shared source-grounded work builder prepares deterministic JSON-quoted
original-source evidence and an exact prompt digest. The existing signed
work-order authority handles HMAC operator approval, atomic nonce consumption,
private SQLite quota, single native dispatch, immutable output receipt, and
crash-ambiguous read-only replay. No retrieved document or model-generated
text can mint a native execution grant.

Run source verification only after the complete wave stack is present:

    python scripts/check_offline_cognition.py --focused
    python scripts/check_offline_cognition.py --full

The full check is wired into the existing Merge Readiness Unit job without
creating any new workflow or admission trigger. It runs for non-draft PRs.
These source tests and contract-only FakeWorker tests never establish real
GGUF weights, licensing, clean target Windows/WSL2 installation or release.

## Operator-signed original source on a real laptop

The optional `manifest_custody.py` and `grounded_cli.py` add a real GGUF
entry path through the existing canonical installer, SQLite work-order owner,
and immutable native replay. The operator must independently approve source
rights and provide a trusted HMAC key; no model text signs itself.

Files are read from a pinned directory fd with `O_NOFOLLOW`, regular-file,
ownership, byte limit, SHA-256 and inode/path-swap checks.

Sign reviewed source bytes with:

    python scripts/sign_offline_ai_source_manifest.py --record /private/record.json --source-root /private/sources --signed-out /private/signed.json --approve-source-rights

Run one approved real local model turn using the signed manifest:

    python -m skeleton.ai.runtime.operational_ai.offline_cognition.grounded_cli --model-root /private/installed-model --state-dir /private/spine --queue-dir /private/work-orders --source-root /private/sources --source-manifest /private/signed.json --tenant local --subject owner --prompt-stdin --approve-native --emit-answer

Both commands require an independently supplied `SKELETON_OFFLINE_OPERATOR_KEY_HEX`
secret kept outside the LLM. Every approval expires in at most one hour.
The source signer never invokes the model; the live CLI refuses uninstalled,
unapproved or mismatched model weights and never retries ambiguous output.

The source suite additionally tests 256 manifest attacks: SHA swaps, foreign
subject signatures, parent traversal and HMAC tampering. Neither the source
suite nor a contract-only FakeWorker qualifies device, license or release.
See `docs/ai/OFFLINE_AI_SIGNED_SOURCE_LAPTOP_RUNBOOK_2026_11_03.md`.
