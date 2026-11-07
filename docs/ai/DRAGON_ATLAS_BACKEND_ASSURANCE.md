# Dragon Atlas backend adapter — source-bound assurance

## Authoritative boundaries

The Atlas backend adapter remains owner/tenant scoped and read-only. A
source-only fixture is not proof of live Mongo CAS fencing, DNS/redirect policy,
robots consent, backend route deployment, native model operation, or Windows
installation. Source text must never become policy, training permission,
publication authority, or an instruction to a model.

## MIME provenance compatibility

Canonical crawl snapshots created before the optional media-inference extension
may have no `mime_inferred`, `declared_content_type`, or
`mime_inference_reason` keys. A source with none of those fields remains a
legacy receipt subject to the other canonical hash, consent, source-status and
evidence-observation checks. If any is present, all three must form a complete
finite decision recognized by `media_probe`; arbitrary reasons, non-boolean
flags, contradictory effective MIME types and unsupported inferred formats
fail closed. The snapshot validator cannot re-sniff bytes not retained.

## CI contract

`.github/workflows/dragon-atlas-backend-bridge.yml` checks out and proves
the exact PR source SHA with read-only workflow permission, compiles the
adapter and source custody surface, and runs:

```sh
PYTHONPATH=.:backend:tests python -m unittest discover -s backend/tests -p 'test_dragon_atlas_bridge.py' -v
PYTHONPATH=.:backend:tests python -m unittest discover -s tests -p 'test_ai_webcrawler_dragon_mime_custody.py' -v
```

Any modifications to the adapter, policy implementation, media probe, core
crawler, shared fixture or these workflows must rerun this qualification.
The fixture tests deliberately rehash tampered snapshots and regenerate source
observations; otherwise failures could be merely digest mismatches.

## Remaining hard gates

Before promoting the draft, separately require canonical AI mirror and
architecture validators, all final-source-head security and merge checks, and
owner-authorized real-backend route tests. Skipped, cancelled, mocked, stale,
ancestor, or merge-ref-only evidence is not a substitute for final-head passes.
Never infer live-network, physical-worker, first-install or release approval
from deterministic source fixtures.

## Cross-plane source-head attribution

The Dragon campaign source, Dragon Atlas frontend, and Jeeves integrated
qualifiers must also checkout `github.event.pull_request.head.sha` and assert
`git rev-parse HEAD` matches that immutable event SHA before executing
untrusted PR code. The default GitHub PR merge ref is distinct from the source
head; merge simulation requires its own explicitly labelled check and may not
substitute for source-head evidence. These workflows retain read-only
credentials and their independent validation scopes.
