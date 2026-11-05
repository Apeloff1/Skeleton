# Studio D First Playable Rebase Notes — #4628

Source branch: feat/studio-d-app-first-playable-journey-20261031-r11
Last observed head: da6cc358a9b0db9c3b5111ba3e503791acbb395b

Scope: original game generation, pinned offline export/ZIP, interactive replay, private save/restore, batch delivery, checkpoint custody, read-only triage, CLI, adversarial fixtures. Includes Path admission, world/replay digests, late artifact substitution.

Status: merge conflict on automated base update. Manual exact-head rebase required.
Floor: ~180 < 250 necessary paths — not a qualifying new draft.
Dependency: coordinate with #4585; do not merge out of order.
Holds: focused pytest (test_app_offline_first_playable_batch*), exact-head CI (Merge Readiness, Backend Quality, E2E, security gates), independent review, no device/release claim.

Next: rebase cleanly to current main, re-verify tree, run focused acceptance, exact-head CI.
