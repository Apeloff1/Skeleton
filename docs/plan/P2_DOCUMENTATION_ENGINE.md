# P2 Documentation Engine

The P2 documentation lane is stacked on the traceability lane and implements the explicit masterplan gaps in **VOL-089 Documentation Engine** and **VOL-090 Generated Documentation**.

Machine authority: `machine/generated_documentation.json`
Generator: `scripts/generate_p2_documentation.py`
Validator: `scripts/check_p2_documentation.py`

## Boundary

Only files declared in the machine manifest under `docs/generated/` are generator-owned. Human-authored architecture, plan, ADR and operations documents remain outside that generated boundary.

Generated documents are derived views. They cannot override machine manifests, runtime behavior, exact-head evidence, or signed accountability.

## Drift model

Every generated output is rendered deterministically from declared repository sources. The document embeds the current Git blob identity of each source. CI reruns the renderer in check mode and fails if the checked-in bytes differ from a clean regeneration.

This lane does not mark `P2-DOC-01`, VOL-089, or VOL-090 complete and does not fabricate implementation or verification sign-off.
