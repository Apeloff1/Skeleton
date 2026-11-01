# Combat objective acceptance — replay-proven game vertical

`python -m skeleton combat-objectives-accept demo` compiles the original
objective source, plays each canonical turn-combat encounter, verifies every
intermediate save, derives earned objective score, checks the final package
and emits a deterministic acceptance receipt.

```sh
python -m skeleton combat-objectives-accept demo
python -m skeleton combat-objectives-accept audit --source-json '<source>'
python -m skeleton combat-objectives-accept verify --report-json '<report>'
```

`accepted` is true only when the canonical campaign is won and every
authored objective was completed. Failed, blocked and unreachable objectives
are reported individually, with replay-verifiable checkpoint lineage and
earned-versus-maximum score. Verification recomputes all gameplay from
authored source; it does not trust a client-supplied report.

This is an offline gameplay acceptance contract, **not** a claim that CI,
security, installation, device, accessibility or release gates have passed.
