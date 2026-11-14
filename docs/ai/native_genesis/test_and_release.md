# Test, qualification and release holds

Focused source and policy tests:
```sh
python -m unittest discover -s skeleton/testing -p 'test_native_genesis*.py' -v
python -m compileall -q skeleton/ai/runtime/operational_ai/native_genesis
python -m skeleton.ai.runtime.operational_ai.native_genesis.cli --vectors
```

The 288 policy cases exercise exact input overrides in 24 domains. Six
accepted and six rejected configurations per domain are serialized as
canonical original JSON. The runner executes the real `GenesisPolicy`
constructor and compares its result to the fixed expected decision. This
is a policy test, not a model-generation simulation.

The focused tests additionally exercise actual original-source parsing,
tokenizer-vocabulary construction, real native CPU model initialization,
checkpoint restoration, actual two-token native inference, one tiny
isolated SGD step, failure classifications and role-separation holds.

**No model weights are checked into the repository.** A passing source
test does not prove an operator executed a complete 432-line SGD run;
that requires its own checkpoint and actual optimizer receipts.

A complete release qualification requires independent success on the
exact final Git SHA for Merge Readiness, Backend Quality, App Foundation
E2E, Workflow Input Security, Sealed Context Guard, Malware Gate,
Artifact Policy, Repository Hygiene, Secret Scanning and Dependency
Review. Also require model rights, real quality comparisons, rollback,
hardware qualification and consumer installation evidence.

Draft PRs are review containers; the latest exact head, not an older
successful commit, determines qualification.
