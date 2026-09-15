# Cooking Promotion — 2026-09-15

## Source comparison

Cooking policy was compared before promotion because the two source blobs are not byte-identical:

- `Apeloff1/Lorebuffa/backend/cooking_routes.py` — `4c366d1c0baa89223758c28f0d4217d1dfa49bc9`
- `Apeloff1/Openworld/backend/cooking_routes.py` — `24575861b7120f036bd646a4ed94950ce27d45ce`

The relevant portable execution path is semantically equivalent. The observed divergence in the shared start-cooking path is presentation-only: Lorebuffa uses an unnecessary `f` prefix for the constant `"Not enough fish of required type"` error string while Openworld uses the same constant string without that prefix.

## Target

- `skeleton/frontier/cooking.py`
- `skeleton/frontier/cooking_adapters.py`
- `skeleton/frontier/__init__.py` public frontier surface

## Promoted policy

- recipe and typed ingredient normalization;
- explicit unlock checks without route or persistence coupling;
- deterministic kitchen-slot selection and completion projection;
- item-consumption plans without inventory mutation;
- identity-aware fish allocation without tacklebox mutation;
- reward plans without user-wallet or XP persistence;
- expiring cooking buffs with injected time;
- narrow adapters into the existing energy and catch-bonus primitives.

## Deliberate evolution and hardening

The source recipes contain fish `min_size` requirements, but the source start-cooking query only matches species/name and does not enforce the declared minimum size. The frontier policy enforces `min_size` during allocation.

The source route counts each fish requirement independently and then deletes matching records. Overlapping requirements can therefore reason about the same pool multiple times. The frontier allocator consumes fish identities once and prevents reuse across requirements.

Cooking jobs now bind the executable recipe semantics with the canonical frontier SHA-256 content digest when cooking starts. Collection recomputes that digest and fails closed if a caller supplies the same recipe ID with changed rewards, buffs, ingredients, timing, unlock level, station, category, difficulty, or name. This prevents claim-time catalog substitution from increasing rewards or injecting stronger effects after the job has already begun.

Additional boundary hardening:

- duplicate fish identities fail closed;
- booleans cannot silently coerce to integer quantities;
- NaN and Infinity fail closed in numeric buff metadata;
- job and buff times must be timezone-aware;
- recipe ID mismatch fails closed at collection;
- same-ID recipe semantic mismatch also fails closed at collection;
- job recipe digests must be normalized lowercase SHA-256 hex;
- string values cannot masquerade as recipe-ID collections;
- recipe `description` and `icon` fields reject non-string coercion;
- timed buffs expire through pure projection rather than database side effects.

## Rejected from kernel

- recipe and ingredient catalogs;
- FastAPI and Pydantic route/request surfaces;
- MongoDB/Motor clients;
- wallet mutation;
- tacklebox deletion/persistence;
- player-kitchen persistence;
- user XP/currency writes.

## Evidence

- `skeleton/testing/test_frontier_cooking_policy.py`
- `skeleton/testing/test_frontier_cooking_integration.py`
- `skeleton/testing/test_frontier_cooking_integrity.py`
- `skeleton/testing/test_frontier_cooking_benchmark.py`
- `scripts/benchmark_frontier_cooking.py`

The benchmark treats timings as observational evidence only. Correctness invariants — including same-ID reward tamper rejection, recipe-digest stability, reward accounting, fish consumption, and buff creation — are gated.

## Selective-promotion boundary

Lorebuffa and Openworld remain authoritative for product catalogs and framework-specific storage. Skeleton owns the hardened, provider-neutral cooking policy and composes it with canonical frontier primitives through adapters only.
