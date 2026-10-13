# Jeeves canonical plan reasoning and verified percentage frontier

**New executable source behavior**:

1. \`ai.cognition.build_plan\` calls the **installed** original-game
   \`PlanVerifier.verify\` and returns actual bounded quality heuristic scores,
   quality issues and policy gate receipts, grounded in a human-supplied
   original game intent. It is not a trained-model evaluation.
2. \`ai.cognition.static_plan\` constructs canonical typed
   \`PlanStep\`, \`StaticPlanDefinition\` and \`PlanVerificationPolicy\` objects
   and invokes the **existing** graph/fact/capability/static budget analyzer.
   Only known read/preview/evaluation capabilities are admissible; no shell,
   network, admin, filesystem-write or other privileged access is allowed.
3. The same call executes real \`simulate_static_plan\` from the installed
   planning engine, optionally fault-injecting one named plan step. This
   simulates errors/recovery deterministically and records modelled effects.
   The simulator does not execute any step as a real tool or job.
4. The Game Studio now presents editable bounded plan sources, original
   vision, DAG steps, starting facts, declared dependencies, capabilities
   and optional failure step. It returns exact policy and decision digests.
5. \`JeevesProductionReview.commit\` now labels the ambiguous failure
   condition where the canonical source writer may have written a file
   but failed during the subsequent acceptance receipt. Such a partial
   failure requires explicit manual reconciliation and fresh review.

**No tests run.** The source implementation registers and exposes actual
existing components. Source code and metadata completion do not imply
that user journeys passed, a product was installed or a model was trained.

### Remaining verified percentages

| Independent denominator | Done | Remaining |
| --- | ---: | ---: |
| Masterplan source implementation status | 414/421 (98.34%) | 7/421 (1.66%) |
| Enterprise qualified volumes | 0/421 (0%) | 421/421 (100%) |
| AI registry complete | 0/9 (0%) | 9/9 (100%) |
| Declared construction gaps closed | 17/17 (100%) | 0/17 (0%) |

**Overall app verification:** unavailable, because no evidence-based
whole-app denominator or independent platform/model/CI qualification
is established. Do not average these unrelated denominators.
