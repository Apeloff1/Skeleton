# Original prompt-to-typed quest authoring

This Studio A workflow accepts an operator's original narrative prompt and a
**typed, explicitly attested** quest plan. It validates the causal DAG, ending
predicates, alternatives and effect tokens against the real canonical quest
engine, produces a source digest and initial playable sandbox quest session,
and offers a CSP-restricted HTML preview. The plan can be supplied by a
model or a human, but this adapter does not invoke a model or claim rights
clearance.

```bash
python -m scripts.studio_prompt_quest_plan_cli --plan-json '{"schema":"skeleton.game_builder.studio_prompt_quest_plan.v1",...}'
```

For an immutable private receipt, use `--publish EXISTING_PRIVATE_DIR`.
To revise a receipt, use `--restore DIR --edit-json '{"kind":"stage_reward",
"id":"search","value":"new_reward"}' --expected-receipt DIGEST
--publish NEW_PRIVATE_DIR`. Revisions are CAS-fenced, recompiled, and never
silently alter an old source or saved quest session. The static Jeeves tool
`studio_original_prompt_quest_plan` requires explicit out-of-band
`allow_authoring=True`. Rights attestation is a statement by the operator,
not verification; native gameplay, external evidence and release remain held.
