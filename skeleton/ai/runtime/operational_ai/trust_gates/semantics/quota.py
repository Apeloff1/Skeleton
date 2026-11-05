"""quota boundary semantics: fail closed on cross-field conflicts."""
from ..contracts import fail

def check(p):
    pending=p["new_prompt"]+p["new_output"]
    if p["prompt_used"]+p["output_used"]+pending > p["tenant_ceiling"]: fail("tenant budget exceeded")
    if pending > p["global_remaining"]: fail("global budget exceeded")
    if p["new_prompt"] > p["tenant_ceiling"]: fail("prompt reservation impossible")
