# VOL-249/250: evidence-bound inquiry and causal modeling

These are executable, source-bound additions within the existing canonical
`skeleton.ai.research` owner. They introduce no new provider, service,
production authority, durable state owner, or cross-plane dependency.

## Hypothesis Engine (VOL-249)

`HypothesisLedger` retains competing hypotheses with explicit falsifiers and
priors. Typed evidence is bound to the active existing
`ResearchSourceRegistry` source identity and SHA-256 content digest, a
method, a direction, a likelihood ratio and declared limitations. Observations
may update **provisional model plausibility**. Simulated and interpreted
evidence are retained but never counted as observations. A numerical ranking
never makes a hypothesis a verified fact; priors and likelihood ratios remain
model assumptions, not calibration evidence. Source correlation is bounded
to one admitted source per hypothesis. Conflicting replay is rejected;
withdrawals cannot be silently rewritten; retracted sources block assessment
until expressly reconciled.

## Causal Knowledge (VOL-250)

`CausalGraph` separates observational associations from directed structural
model claims. Every graph edge has source, digest, method and assumptions.
Associations have no causal coefficient and cannot propagate simulated
interventions. Structural edges are acyclic, unique per directed pair,
capacity-bounded, and require explicit coefficient. Directed hypotheses need
explicit what-if opt-in; unresolved confounders deny relevant intervention
even when opt-in is true. Retraction or correction invalidates current graph
snapshots and simulations. A local simulated intervention propagates bounded
deltas in topological order and always returns
`SIMULATION_NOT_OBSERVATION` and `observed=False`; no real-world action
is executed.

## L00-L13 owner and qualification boundaries

L00: source requirements; L01: stable typed identities; L02: canonical
research owner; L03: process-local only, no durable recovery claim; L04:
bounded deterministic lifecycle; L05: rights-bound source admission;
L06: retraction, replay and cycle denial; L07: focused positive and negative
regressions; L08: independent empirical calibration and identification still
required; L09: content-bound SHA256 receipts; L10: bounded nodes, events,
ratios and numerical magnitudes; L11: no new storage migrations or release
artifacts; L12: no production action authority; L13: independent current-head
tests plus original security, release, device and integration holds.

### Qualification commands

```bash
python -m unittest discover -s skeleton/testing -p 'test_hypothesis_engine.py' -v
python -m unittest discover -s skeleton/testing -p 'test_causal_knowledge.py' -v
python -m pytest -q skeleton/testing/test_research_lineage.py skeleton/testing/test_research_system_acceptance.py
python scripts/check_architecture_map.py
python scripts/check_ai_app_construction.py
python scripts/check_capability_interfaces.py
python scripts/check_provider_bootstrap.py
python scripts/check_enterprise_ai_superiority.py --json
python scripts/check_enterprise_ai_implementation_notes.py --json
```

The originally declared `planned:` test paths for VOL-249 and VOL-250 now
have matching executable regression sources in this draft. This does not
promote MDM-058, prove model calibration or first-install readiness, or
retroactively alter the canonical signed source ledger.

## MDM-058 cross-volume game-design probe bridge (VOL-249..252)

The pure `skeleton.ai.research.game_design_probes` planner now composes the
hypothesis ledger, causal DAG, and the canonical P1-INTEL-03
`skeleton.intelligence.strategy_registry` control decision for a named
original-game project and falsifiable metric. It binds both models to the
**identical** source registry instance. It validates all live source digests,
retraces both source snapshots before sealing a deterministic SHA-256 receipt,
bounds candidate/history iteration, and preserves critical-risk verification,
budget and value-of-information stops. An optional model preview is always
`SIMULATION_NOT_OBSERVATION`, with explicit opt-in for hypothesized edges and
no bypass for confounding.

The return object is **non-executable**, even when upstream self-reported
confidence passes a stopping threshold. No gameplay is modified, no research
source is ingested automatically, and no authority passes to a provider,
installer, builder, world runtime, or release decision. Future work requires a
separately reviewed, policy-bound Jeeves proposal adapter and independent live
experiment/device evidence. Provenance here is source-custody, **not** proof
that a claimed empirical observation is genuine.

Focused validation after complete build:
```sh
python -m unittest discover -s skeleton/testing -p 'test_game_design_probes.py' -v
python -m unittest discover -s skeleton/testing -p 'test_ai_git_knowledge.py' -v
```

The Git knowledge fixture now constructs its synthetic secret marker at
runtime rather than leaving key-shaped bytes in tracked test source; rejection
behavior remains covered without exempting any secret-hygiene scanner pattern.

## Canonical AI-only ownership and native fixture portability

New research modules remain only under `skeleton/ai/research`, the established
canonical AI namespace. The legacy `skeleton/research` remains unchanged
because a new legacy mirror requires new signed entries in
`machine/ai_file_tree.json`; this PR cannot silently claim migration
authority. The existing Jeeves, Forge and audio mirror deficits remain CI
blockers, not waived or inherited passes.

The flight-HTTP and Git source-custody tests now select the caller's home
directory as their temporary-file parent instead of a local-only path.

The GGUF/SQLite custody guard traverses all ancestor directories using
descriptor-based no-follow access and denies group/other-writable ancestors.
Consequently test fixtures cannot be placed under `/tmp` merely because the
leaf is private. The two hosted portability fixtures use `Path.home()` as
their parent; if that home is not private enough, tests correctly fail without
loosening `open_trusted_root`. The branch still requires real hardware custody
and native runtime acceptance before release.

The native SQLite/flight acceptance workflow additionally exercises the
research knowledge plane, flight admission, local inference daemon, daemon
operator and durable Jeeves CLI. Their synthetic fixtures now also use
mode-`0700` temporary subdirectories under the caller's home rather than
requiring a fixed container identity. This leaves descriptor-based no-follow
and writable-parent rejection active and does not waive Windows, GGUF or
hardware-pressure qualification.
