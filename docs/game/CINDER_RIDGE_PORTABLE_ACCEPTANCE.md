# Cinder Ridge — executable laptop-first consumer acceptance

The critical-path acceptance is a real, original two-chapter game played
through the numbered consumer interface, not a static content inventory.

From the repository root, with Python 3.11+ available:

    python -m skeleton.game.gameplay.ridge_rescue consumer portable-smoke

The command creates a deterministic Python zipapp from the original game
sources, verifies the archive, runs it from a disposable directory with an
empty PYTHONPATH, selects each action from the canonical game engine, quits
after a partial chapter, restarts in a separate process, earns the declared
chapter endings, replays the SQLite audit, exports the earned campaign and
rejects a post-victory invalid mutation without changing the save.

For the source-checkout path, run:

    python -m skeleton.game.gameplay.ridge_rescue consumer smoke

For a manual Windows consumer pass, use scripts/windows/cinder-ridge.cmd.
On the target Windows laptop, also run the portable-smoke command in a
normal Command Prompt and retain its JSON evidence and exact Git SHA.
The portable zipapp still requires a separately installed Python 3.11+.
Neither the command nor the source tree is a signed Windows installer.

These tests do not prove Windows behavior until run on Windows. They do not
prove target hardware compatibility, security gate success, installer
qualification or release readiness. The exact-head mandatory GitHub CI
checks and independent review remain separate release gates.
