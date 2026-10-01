# Architecture Control Index

<!-- generated-document: do-not-edit -->
<!-- generator: p2-docs/0.1.0 -->
<!-- source-git-blob: machine/architecture_rule_registry.json@a9fe0bd88e6efc096b58e49d2af4d885ab0015bc -->
<!-- source-git-blob: machine/architecture.json@cf4b764e21098a890fa624c2d2211f93e664c76b -->
<!-- source-git-blob: machine/adr_index.json@b713a5e03d4a4f525066b608bd6d4c88622cc166 -->

> Generated from architecture machine authority. Regenerate this file after source changes; do not hand-edit rule or ADR listings.

## Canonical topology

- Canonical roots: **8**
- Architecture zones: **8**
- Registered fitness rules: **13**
- ADR records: **1**

## Registered architecture rules

| Rule | Validator | Severity | Waivable |
| --- | --- | --- | --- |
| ARCH-ADR-INDEX | `scripts/check_architecture_adr_index.py` | blocking | false |
| ARCH-AI-TREE-PARITY | `scripts/check_ai_file_tree.py` | blocking | true |
| ARCH-BOUNDARY-IMPORTS | `scripts/check_architecture_boundaries.py` | blocking | true |
| ARCH-CONTRACT-CONFORMANCE | `scripts/check_architecture_contract_conformance.py` | blocking | false |
| ARCH-DOC-AUTHORITY | `scripts/check_architecture_doc_contradictions.py` | blocking | true |
| ARCH-MANIFEST-REFERENCES | `scripts/check_architecture_manifest_references.py` | blocking | false |
| ARCH-MAP-CONSISTENCY | `scripts/check_architecture_map.py` | blocking | false |
| ARCH-OWNERSHIP | `scripts/check_architecture_ownership.py` | blocking | false |
| ARCH-PACKAGED-WHEEL | `scripts/check_architecture_packaged_wheel.py` | blocking | false |
| ARCH-PYTHON-LAYERS | `scripts/check_architecture_package_layers.py` | blocking | true |
| ARCH-RULE-REGISTRY | `scripts/check_architecture_rule_registry.py` | blocking | false |
| ARCH-RUNTIME-SUPERVISION | `scripts/check_architecture_runtime_supervision.py` | blocking | false |
| ARCH-SCOPE-FREEZE | `scripts/check_ai_scope_freeze.py` | blocking | false |

## Architecture decisions

| ADR | Status | Document | Masterplan refs |
| --- | --- | --- | --- |
| ADR-0001 | accepted | `docs/adr/ADR-0001-p2-architecture-governance.md` | VOL-002, VOL-051, VOL-052, VOL-053, VOL-054, VOL-055, VOL-058, VOL-116 |

Generated listings are navigational only; machine manifests remain authoritative.
