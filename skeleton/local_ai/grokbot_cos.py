"""
Run GrokBot as Chief of Staff. Dispatch only. Mine, rewrite NEXT, fire factory, never implement or push.
"""
from __future__ import annotations

from .seam_runtime import admit, stamp

ROLE = "dispatch"
_BLOCKED = {"implement", "push", "merge"}


def process(data: dict) -> dict:
    refused = admit("grokbot_cos", data)
    if refused:
        return refused
    action = data.get("action")
    if action in _BLOCKED:
        return {"ok": False, "error": "role is dispatch only", "card": "grokbot_cos", "role": ROLE}
    if action is not None and not isinstance(action, str):
        return {"ok": False, "error": "action is invalid", "card": "grokbot_cos"}
    body: dict = {"role": ROLE}
    if action is not None:
        body["action"] = action
    return stamp("grokbot_cos", data, body)
