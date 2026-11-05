# Conflicted PR Heads — 2026-11-05

The following open PRs returned merge conflict on automated base update:

- #4628 feat(studio-d): integrate offline original-game first playable... (dirty)
- #4636 fix(assets): reject nonfinite OBJ vertices... (stacked)
- #4674 feat(game): original source-bound scene market... (conflict)

Manual exact-head rebase onto current main is required. Preserve all floors, security, and review gates. No automatic conflict resolution or padding.

After rebase, re-trigger exact-head CI (Merge Readiness, Backend Quality, Secret, Dependency).
