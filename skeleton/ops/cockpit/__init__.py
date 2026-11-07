"""Cockpit ops-hardening toolkit.

Python port of the verification/ops scripts from the sibling
``Apeloff1/hyperforge-cockpit-sota`` (``scripts/*.mjs``):

* :mod:`.brand_check`      - share-card / X game-card brand asset gate
* :mod:`.browser_guard`    - loopback-only URL + confined output path checks
* :mod:`.smoke_verdict`    - browser smoke verdict hashing, baseline diff, exit codes
* :mod:`.migration_plan`   - basename-keyed SQL migration bookkeeping
* :mod:`.sign_out_plan`    - preview vs deployed sign-out sequencing (asyncio)
* :mod:`.app_env`          - ``.grok/app-env.json`` VITE_* env carrier + runner
* :mod:`.qa_flight`        - pure evaluator for steering/controls flight probes

Everything here is pure / side-effect-light so it is unit-testable without a
browser; the CLI (``python -m skeleton.ops.cockpit``) wires them together.
"""

from .brand_check import MAX_CARD_BYTES, BrandFinding, compute_brand_warnings
from .browser_guard import GuardError, checked_output_path, checked_url
from .migration_plan import Migration, migration_name, pending_migrations
from .smoke_verdict import (
    baseline_comparison,
    compare_to_baseline,
    exit_code_for,
    normalized_body_text_hash,
)
from .sign_out_plan import SignOutError, run_pre_sign_in_sign_out, run_sign_out
from .app_env import merge_app_env, parse_app_env, read_app_env
from .qa_flight import FlightProbe, evaluate_flight

__all__ = [
    "MAX_CARD_BYTES",
    "BrandFinding",
    "compute_brand_warnings",
    "GuardError",
    "checked_output_path",
    "checked_url",
    "Migration",
    "migration_name",
    "pending_migrations",
    "baseline_comparison",
    "compare_to_baseline",
    "exit_code_for",
    "normalized_body_text_hash",
    "SignOutError",
    "run_pre_sign_in_sign_out",
    "run_sign_out",
    "merge_app_env",
    "parse_app_env",
    "read_app_env",
    "FlightProbe",
    "evaluate_flight",
]
