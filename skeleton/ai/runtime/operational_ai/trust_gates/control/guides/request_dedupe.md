# request_dedupe — AI runtime control-plane lifecycle

This is an executable local AI lifecycle controller. It refuses ambiguous
identities, duplicate transitions, unbounded allocations or authority that
was never explicitly granted.

## Trust boundaries

- Caller is responsible for providing independently authenticated inputs.
- An in-process lock is **not** a distributed or durable commit guarantee.
- Check `request_dedupe.py` against the state-machine regression tests before integration.
- Any real model activation must still use the canonical GGUF source-bound
  installer and exact approved model/tokenizer hashes.
- A workflow's success never replaces real-model quality, device, installer,
  security-gate or independent human-review evidence.

## Integration plan

Use this controller only behind the existing offline native runtime owner.
Preserve the existing SQLite authoritative chat and journal custody, the
policy-bound tool executor, local-only transport and model epoch fences.
Avoid inference, tool or deployment side effects in the preflight stage.
