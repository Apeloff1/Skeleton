# Serving and tokenizer synergy

packet: SERVE-TOKEN-SYNERGY-20261008
parent: #80
stored_prose: 0

Composes the #3537 closed-loop serving fence with the #3535 tokenizer identity law.
A plan receipt cannot be observed under a different tokenizer digest.
An oversized prefill denial does not open the observe fence.
Checkpoint bind refuses a feedback snapshot paired with a foreign tokenizer digest.

Run:

```bash
python -m unittest tests.flgb.test_serving_token_synergy tests.flgb.test_serving_control_adversarial_boundaries -v
```
