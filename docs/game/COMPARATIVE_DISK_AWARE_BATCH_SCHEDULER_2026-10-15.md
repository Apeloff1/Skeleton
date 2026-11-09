# Disk-aware concurrent comparative emulator scheduling — 2026-10-15

The comparative study maintains **at most ten live native games**, but adding multi-GiB disc material requires *smaller waves* on hosts without sufficient temporary storage. The new `_storage_waves` resource gate separates each at-most-10-title study cohort into one or more sequentially executed waves without changing the original study order or ever fabricating game observations.

Before launching a wave, the operator runner reads actual free temporary disk space (the same platform default temporary volume used by the native emulator). It budgets no more than one third of that free disk and no more than 16 GiB to the comparative batch, allowing a conservative estimate of **two copies of every game’s declared media bytes plus 128 MiB of sandbox/core/firmware overhead per worker**. Inline single-file games are pessimistically charged the existing 16 MiB maximum even if smaller.

The scheduler then fills waves in input order, admitting up to the `max_active` value from the manifest (never more than ten), and starts each wave through a fixed-size `ThreadPoolExecutor`. If a single game cannot fit the declared budget, the batch fails before starting it. Previous successful batches are not relabeled as completed failures; native failures remain explicit per-game errors. The report exposes the effective maximum allowed concurrency, free temporary bytes at preflight, reserved budget and per-batch wave sizes so users can inspect why only a few game cores ran at once.

Examples:
- Ten tiny cartridge games on an adequately provisioned host can still run simultaneously.
- Three roughly 2 GiB game images with 30 GiB temporary free space form two waves (2 games, then 1 game).
- If disk is too small for a single pinned game, the runner rejects it rather than using an unsafe fallback.

This does **not** enforce RAM/disk quota against other processes or replace native process resource limits; a system may change between preflight and materialization, in which case the existing sandbox/materialization checks still fail closed. Rights-cleared native sources and approved libretro installations are required. The associated `tests/test_game_comparison_scheduler.py` adds source-only wave budgeting tests; live disk and emulation tests remain unverified.
