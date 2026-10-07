# Architecture Rule Registry

<!-- machine-git-blob: machine/architecture_rule_registry.json@a9fe0bd88e6efc096b58e49d2af4d885ab0015bc -->

This registry implements the P2 masterplan gaps in **VOL-055 Architecture Linter** and **VOL-116 Architecture Fitness Functions** without creating a new architecture domain.

Machine authority: `machine/architecture_rule_registry.json`
Validator: `scripts/check_architecture_rule_registry.py`
Canonical owners/zones: `machine/architecture.json`

## Contract

Every architecture validator is registered with a blocking rule ID, canonical root ownership, affected architecture zones, direct execution command, ADR change-control requirement, and an explicit waiver policy.

The validator discovers every `scripts/check_architecture*.py` file plus the AI file-tree and scope-freeze guards. A new architecture validator that is not registered fails closed.

## Waivers

Waivers are exceptional, rule-specific, and time bounded. A waiver is valid only when the rule allows it and the record includes an independent approver, full Git SHA, evidence references, supported identity-bound signature method, and an existing ADR document. Expired waivers fail the registry.

Rules that protect canonical map integrity, the registry itself, or the masterplan breadth freeze are not waivable.

## Masterplan relationship

The registry verifies that its named implementation targets remain literal gaps in VOL-055 and VOL-116. If the masterplan changes those obligations, the registry must be reconciled rather than silently continuing under stale assumptions.

This registry inventories architecture checks. It does not aggregate them into maturity evidence, replace the master build sequence, or grant completion authority.
