# P3-T2 Native Model Development and Training

P3-T2 begins from the 197-volume queue left by the merged P3-T1 autonomous-engineering frontier.

It schedules **24 volumes** and leaves **173 explicit**.

The tranche is intentionally AI-core:

1. data, lineage, dataset registry, quality and synthetic-data foundation;
2. model/data rights, license and MBOM provenance;
3. local training control, distributed topology, checkpoint/resume, elastic recovery, observability and evaluation gates;
4. post-training, deterministic RL environments, curriculum and verifier-model programs;
5. model lifecycle, deprecation and migration.

Hosted model APIs are not accepted as evidence for this tranche. The acceptance target is a credential-free local training transaction whose dataset, checkpoints, model artifacts, evaluation decisions and lifecycle transitions are all deterministic and provenance-bound.

No P3-T2 task can self-promote masterplan maturity, completion checkboxes or independent signatures.

Run:

    python scripts/check_p3_native_training_execution_map.py --json
    python -m pytest -q tests/test_p3_native_training_execution_map.py
