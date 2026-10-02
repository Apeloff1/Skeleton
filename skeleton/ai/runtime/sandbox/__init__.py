"""Execution sandbox (B082/B086): process + filesystem isolation, sanitizers
and injection detection for untrusted tools, generated code and model input.

Complements the policy mediator in :mod:`skeleton.security.generated_code_sandbox`
(which decides *whether* an effect is granted) with the enforcement layer
that *contains* it.
"""
from .errors import *  # noqa: F403
from .fs import FsJail, JailPolicy, check_relative
from .injection import InjectionReport, detect, guard, quarantine
from .process import ProcessLimits, ProcessResult, run_isolated, scrub_env
from .sanitizers import (
    escape_html,
    hidden_characters,
    redact_secrets,
    safe_json_loads,
    sanitize_filename,
    sanitize_structure,
    sanitize_text,
    strip_ansi,
)

__all__ = [
    "FsJail", "InjectionReport", "JailPolicy", "ProcessLimits", "ProcessResult",
    "check_relative", "detect", "escape_html", "guard", "hidden_characters", "quarantine",
    "redact_secrets", "run_isolated", "safe_json_loads", "sanitize_filename",
    "sanitize_structure", "sanitize_text", "scrub_env", "strip_ansi",
]
