# Offline AI bootstrap identity and readiness

This package owns **the executable AI principal and checkpoint binding**, not
any game data. `state.identity.json` is created only inside a private, newly
provisioned state directory before SQLite or a model runtime is opened. It
pins a tenant, user, approved model digest and model-bound tokenizer digest.
A different principal, model or tokenizer cannot silently adopt a conversation
store created by the first principal.

The binding is an owner-private identity record with a checksum, **not a
cryptographic signature or protection against a malicious same-UID process**.
`establish_binding` refuses to attach an unbound existing chat, memory, audit,
WAL or session-lock state. Operators must independently review old state and
perform a documented, separately approved migration; the runtime never guesses.

From a clean operator-provisioned private directory:

```bash
python -m skeleton.ai.runtime.operational_ai.deployment.boot.cli bind \
  --model-root /trusted/approved-model --state-dir /private/ai-state \
  --tenant local --user operator --approve-new-state
python -m skeleton.ai.runtime.operational_ai.deployment.boot.cli doctor \
  --model-root /trusted/approved-model --state-dir /private/ai-state \
  --memory-key-file /private/ai-keys/memory.key --tenant local --user operator
```

The read-only doctor checks installed source digests and receipt, private key
custody, state ownership and local llama.cpp presence. No inference occurs, no
model is downloaded, and the report deliberately says `release_certified=false`.
The production `gguf_chat` launcher enforces the same binding before the
conversation store opens; it also enables cross-process session serialization.

Strong (>=32 character) bearer token must be set in
`SKELETON_LOCAL_AI_BEARER` before `--serve`; the server binds only literal
loopback, refuses browser origins, ambiguous HTTP framing, and caps concurrent
connections. Neither the binder nor the API creates or grants tool privileges.

Remaining qualification includes an independently approved model license,
true local GGUF inference, machine resource measurements, full exact-head CI,
security review and install/restore drills.

## Actual native-inference proof

The read-only doctor cannot establish model execution. Use an independent
operator-initiated live smoke **after** installation:

```bash
python -m skeleton.ai.runtime.operational_ai.model.gguf.probe_cli \
  --model-root /trusted/approved-model --context-tokens 2048 \
  --new-tokens 16 --gpu-layers 0
```

The command calls llama.cpp on installed, verified model bytes and reports a
hash of the output, native token usage and elapsed time. It never substitutes a
mock, downloaded model or generated padding. Passing this short smoke does not
prove answer quality, consistency, context length, GPU readiness or release.
