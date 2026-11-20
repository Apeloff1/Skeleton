# Local Jeeves Docker — physical synthetic actor writer-epoch fencing

**Review-only. Explicit opt-in. Offline synthetic data only.**

This source augments the previously implemented disposable Mongo three-voter
Docker quorum, failover, lost-majority denial, and repaired-journal policy
qualification. It DOES NOT enroll or migrate the production conversation
writer or the Jeeves memory writer, and does not edit any live Mongo database.

## Why a separate test is necessary

An observed replica-set primary, a running chat HTTP route, and even a
journal-requested `w=majority` synthetic write cannot prove that the
backend conversation writer and engine memory writer share a valid actor
epoch. The existing canonical `MongoCanonicalSourceEpoch` uses an
actor-scoped **even/stable → odd/writing → even/stable** majority-acknowledged
compare-and-swap discipline; concurrent or crashed writers must not
silently regain authority. A real network failover is essential to
challenge that invariant.

## Run explicitly against synthetic nodes only

Use a pre-existing independently verified offline four-image archive and
exact-ID binding overlay whose immutable Mongo image already exists locally.

```sh
python scripts/local_ai_docker.py --mode cpu \
  qualify-synthetic-mongo-failover \
  --directory /private/offline-images \
  --overlay-directory /private/offline-compose \
  --expected-receipt-sha256 YOUR_INDEPENDENT_VERIFIED_SHA256 \
  --allow-synthetic-database-writes \
  --exercise-synthetic-writer-epoch
```

The two opt-in flags are separate. The first permits only the already
isolated, disposable synthetic Mongo database writes. The second adds
actor epoch CAS assertions to that physical test. Without either
approval, nothing is started or written.

The full existing synthetic Docker isolation is still mandatory:
- Exact immutable Mongo image ID from an admitted four-image transfer receipt.
- Local Linux Unix Docker socket; remote daemon overrides denied.
- No image pull, published port, externally attached network, host volume,
  Mongo production URI, model acquisition, or user data.
- Three bounded, dropped-capability containers with memory-only Mongo
  storage and random test-scoped identities.
- Independently verified primary election, journaled-majority policy,
  physical failover, minority write refusal, healed majority and cleanup.

The actor test writes only to `skl_ephemeral_qualification` and its
`synthetic_canonical_epoch` collection inside these disposable Mongo
containers. Document keys and tokens derive only from the random synthetic
challenge; no real tenant ID, account ID, chat message or memory text is used.

## Physical cross-process CAS sequence

1. On the actual elected three-voter synthetic primary, create TWO
   independent actors at `epoch=2, phase=stable, writer_token=null`.
   Both creations use an explicitly journal-requested majority write.
2. Acquire actor 0 with a majority-journaled `findAndModify` compare-
   and-swap: epoch 2→3 and phase stable→writing.
3. Start a separate mongosh invocation as another synthetic owner.
   It must be unable to acquire the already-written epoch 2 and unable
   to complete epoch 3 using its stale writer token.
4. Finish actor 0 using the original valid writer token; epoch 3→4
   with stable phase and no token. Require an exact primary-bound
   **linearizable** read of the completed even epoch.
5. Acquire actor 0 again at epoch 4→5 using another token, but deliberately
   leave its phase WRITING. This models an interrupted canonical writer,
   **not** a safely completed operation.
6. Stop the elected synthetic primary using its exact original Docker
   container ID. The original three-node physical test independently
   confirms a different primary is elected from the surviving majority.
7. On that *new physical primary*, a linearizable read must still show
   epoch 5, WRITING, and the original token. A competing writer cannot
   acquire the stale even epoch and cannot clear the odd epoch using
   another token. **No automatic lease takeover or quarantine release.**
8. Actor 1, with a different key, must still successfully acquire
   epoch 2→3, complete 3→4 and replay its even stable state while actor 0
   remains quarantined. This checks actor-scoped rather than global
   suspension.
9. The original Docker test proceeds to secondary quorum-loss denial,
   reconciliation of its two surviving members, and a third synthetic
   write. All scoped disposable test assets are cleaned only after
   strict label, name and immutable-ID verification.

Each Mongo call is bounded, returns a strict JSON allowlist, checks exact
acknowledgement, and emits no raw token, actor key, hostname, command
text or database document in the final operator report. Any wrong token,
missing quorum, stale primary, changed epoch or forged extra receipt
fails the test closed.

## What a passing test does NOT prove

| Domain | State after a synthetic pass |
|---|---|
| Real Mongo majority-CAS and actor-scoped fencing in disposable test | Synthetic physical evidence only |
| Real backend writer bound to canonical `MongoCanonicalSourceEpoch` | Unverified |
| Real Jeeves engine memory writer bound to the same epoch | Unverified |
| Complete external writer registry and mixed-version writer exclusion | Unverified |
| Authorized migration of existing actor source epochs | Unverified |
| Durable power-loss recovery on independent machines | Unverified |
| Coherent Mongo / SQLite / Chroma recovery | Unverified |
| Protected Jeeves chat with trusted tokenizer and bounded reviewer | Unverified |
| GPU / WSL2 / native GGUF / release provenance | Unverified |

The actual production application still has a standalone Mongo topology.
Do not activate the production epoch overlays or claim full deployment
readiness merely because this synthetic test passes. The test cannot
approve a merge, release, database migration or container transition.

## Exact-head source qualification

```sh
python -m compileall -q \
  scripts/local_ai_synthetic_epoch_fence.py \
  scripts/qualify_local_ai_mongo_quorum_docker.py \
  scripts/local_ai_docker.py \
  skeleton/testing/test_local_ai_synthetic_epoch_fence.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_local_ai_synthetic_epoch_fence.py \
  skeleton/testing/test_local_ai_mongo_quorum_docker.py \
  skeleton/testing/test_local_ai_mongo_majority.py
```

These unit tests exercise the Python orchestration with hostile fixtures,
not a real local Docker daemon. Real physical evidence additionally
requires running the explicit operator command on an operator-owned
Linux host with already verified immutable local Docker images. Do not
claim the physical test passed until a real exact-head receipt exists.
