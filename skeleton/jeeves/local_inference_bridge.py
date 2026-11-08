"""Legacy Jeeves local inference compatibility bridge.

This module does not own a model loader or provider runtime. It must not
fabricate a successful model response; callers must use the canonical
skeleton.provider_runtime boundary for guarded inference.
"""

class Bridge:
    """Fail-closed compatibility surface for obsolete direct dispatch."""

    def dispatch(self, cmd: dict, cas: str) -> dict:
        if not isinstance(cas, str) or len(cas) < 16:
            raise PermissionError("CAS required")
        if not isinstance(cmd, dict):
            raise TypeError("command must be a mapping")
        raise RuntimeError(
            "LOCAL_INFERENCE_NOT_BOUND: use guarded skeleton.provider_runtime; "
            "legacy Jeeves bridge has no verified model or tokenizer"
        )
