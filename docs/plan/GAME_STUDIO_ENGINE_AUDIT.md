# Original game-engine audit and learning verification

This pass adds a real, bounded, source-replay verification harness for the
43 advanced reference studio engines. It is **not** native emulator hardware
validation, production training, or independent evidence of model improvement.

## Run the original game engines instead of trusting registry status

```sh
python -m skeleton.jeeves.game_studio_engine_audit \
  --engines all --max-steps 8 \
  --output /private/engine-audit.json
```

For each registered engine, this command executes its actual original-game
startup, independently verifies the canonical replay, checks authored scene
identity where supported, tries real bounded player commands, runs those
controls through Jeeves's emulator-compatible episode environment, restores
the hashed learning snapshot into a separate instance, and projects honest
visual telemetry. Any failure produces a named blocked engine with a concrete
failure stage. The CLI returns failure if even one selected engine blocks.

With source rights and explicit operator admission, the same audit can
**also execute actual candidate Q-learning updates**:

```sh
python -m skeleton.jeeves.game_studio_engine_audit \
  --engines economy narrative audio --max-steps 6 \
  --train-episodes 2 --authorized --rights-cleared \
  --output /private/new-engine-training-audit.json
```

The output is a new, exclusive, SHA-addressed private file, with independent
gameplay and policy snapshots, actual candidate update counts, failures,
and absolute nonclaims: no live neural weights changed, no native hardware
certification, no automatic promotion. It does not silently rewrite the
production Jeeves checkpoint or fabricate playable worlds for absent engines.

A registry count of 43/43 is only the **source-executable reference surface**.
A true 100% production milestone still requires physically rendered worlds,
actual audio output, real host networking, durable filesystem save support,
measured hardware-era runtime profiles, release readiness, end-to-end app
validation, user-approved model training and independent quality review.

## Immediate validation

```sh
python -m unittest tests.test_game_studio_engine_audit
python -m unittest tests.test_game_builder_advanced_product_engines
python -m unittest tests.test_game_builder_advanced_remaining_product_engines
```

The above are operator commands; repository authoring by GitHub connector alone
is not evidence they have been run or passed.
