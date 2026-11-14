# LearningRate — native model initialization policy boundaries

**Domain:** `learning_rate`

This domain supplies twelve fully specified, original policy-decision cases:
six configurations admitted by the constructor and six malformed, unsafe or
unapproved configurations that must be rejected before model allocation.

The exercised policy is `GenesisPolicy`, the same constructor used by the
actual offline source-derived TinyTransformer initializer. Each test parses
the complete canonical JSON source, executes the real policy method,
compares the observed decision to a fixed expected result, and independently
verifies the candidate-only, CPU-only and no-auto-promotion boundary.

Unlike placeholder unit tests, vectors carry precise override inputs
and are executed as independent cases. Tampering with the expected outcome,
source schema or unrecognized metadata must be detectable. The suite is
valid only when all 288 vectors across 24 categories are present and pass.

A policy acceptance proves only that configuration is well-formed. It
does not establish model accuracy, trained weights, GPU support, safe model
release, hardware reproducibility or final-head GitHub CI success.
