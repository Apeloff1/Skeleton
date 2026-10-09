# AI-tree fill 1.8.0

Drop-in capability bodies for `Apeloff1/Skeleton` `skeleton/ai`.

The live tree on main is a governed mirror plus a schema-only `CapabilityMap`. Intent never meets evidence, so resolution stays fail-closed and the tree cannot answer "is this capability live". This package stamps evidence by executing the bodies.

## Run

```bash
cd ai-tree-fill
python3 -m unittest tests.test_tree_fill
python3 -m ai_tree_fill status
```

Exit 0 and `"functional": true` means all 48 catalog ids resolved `available`. Unknown organs still return `hit=0`.

## Do not

- Do not delete migration sources. Relocation is not cutover.
- Do not stamp `G=10` without a trajectory.
- Do not store sentences in the pointer mesh.
- Do not add a coin, a chain, or a third router.
- Do not merge this branch over operator `deck.py`.
