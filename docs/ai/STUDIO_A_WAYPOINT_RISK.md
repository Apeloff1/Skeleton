# Studio A: source-bound hazard-aware waypoint planning

The existing waypoint itinerary optimizes moves through a collision-checked
authored grid. This complementary preview minimizes **authored hazard contacts**
before move count, subject to an explicit maximum contact budget and the
canonical starting-health lease. It reuses the same offline world and hazard
source functions as the playable encounter renderer.

Operator CLI:

```sh
python -m scripts.studio_waypoint_risk_cli \
  --project YOUR_ORIGINAL_PROJECT --expected-source SHA256_HEX \
  --start '[1,1]' --waypoints '[[3,3]]' \
  --max-hazard-contacts 0 --html-sha256
```

Pass `--publish PRIVATE_DIRECTORY` to atomically create a mode-0600 receipt,
or `--restore PRIVATE_DIRECTORY` to replay an existing receipt against the
live source. Publication never overwrites existing data. Jeeves can call the
read-only `studio_original_waypoint_risk` tool with the exact typed request
schema and out-of-band authorization. Both return deterministic digest-bound
proofs, not claims of player traversal, native combat, or release readiness.

The route algorithm counts **every entry** into an authored hazard cell, even
when the same cell is revisited. It rejects malformed cells, mismatched source
digests, fatal risk budgets, unreachable waypoints, oversized requests and
forged persistence receipts. A route can be compiled into the existing
direction-event vocabulary for subsequent playable walk verification, but the
preview itself does not claim that runtime verification has occurred.
