"""main-guard: guard rails for many agents committing directly to ``main``.

Components (each has a CLI under ``scripts/main_guard_*.py`` and
``python -m skeleton.main_guard <command>``):

* ``watcher`` / ``notice`` — post-push CI watcher attributing failures to
  commits/authors and rendering fix-forward notices (dry-run unless ``--post``).
* ``bisect`` — first-bad-commit search that always restores HEAD/bisect state.
* ``mirror`` — ``skeleton/`` -> ``skeleton/ai/`` mirror drift checker driven by
  ``machine/ai_file_tree.json``.
* ``board`` — read-only board truth report for open pull requests.
* ``prepush`` / ``test_map`` — pre-push helper: rebase, targeted tests,
  force-push refusal and optional drift check.

The package is repository tooling only; it imports nothing from the runtime.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
