# Serving and tokenizer synergy

packet: SERVE-TOKEN-SYNERGY-20261008
parent: #80
stored_prose: 0

Composes the #3537 closed-loop serving fence with the #3535 tokenizer identity law.
A plan receipt cannot be observed under a different tokenizer digest.
An oversized prefill denial does not open the observe fence.
Cycle: `ServingTokenCycle.admit_text` takes prompt length from `encode_ids`. `observe_and_record` writes telemetry only after observe. A full window does not train. Cohort digest binds the tokenizer identity.

Run:

```bash
python -m unittest tests.flgb.test_serving_token_synergy tests.flgb.test_serving_control_adversarial_boundaries -v
```
