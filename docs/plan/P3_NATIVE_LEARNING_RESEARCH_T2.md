# P3-T2 Native Learning & Research Frontier

This stacked tranche starts from the **197-volume queue** left by the bounded
P3-T1 autonomous-engineering frontier.

It schedules **52 volumes** and leaves **145 explicit**. The tranche is focused
on the provider-independent AI itself rather than hosted-provider integrations:

1. data, lineage, quality, datasets, synthetic data and content addressing;
2. native training control, distributed training, checkpoint/recovery,
   observability, evaluation gates, post-training, RL curricula and verifier models;
3. local multimodal ingestion, vision, document vision, audio, speech, video and retrieval;
4. research evidence, literature/citation graphs, reproducibility, statistics,
   hypothesis and causal knowledge;
5. model/agent evaluation, long-horizon benchmarking, contamination auditing,
   human evaluation and card systems;
6. local serving memory/eviction/KV/prefix/speculative-inference controls;
7. build/evaluation/research compute queues.

The first owner is ready. Downstream owners remain dependency-blocked until
exact-head implementation evidence lands.

No task may promote masterplan maturity or sign independent verification.

Run:

    python scripts/check_p3_native_learning_execution_map.py --json
    python -m pytest -q tests/test_p3_native_learning_execution_map.py
