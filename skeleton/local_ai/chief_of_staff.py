"""
Operate as Chief of Staff and secretary for Apeloff1/Skeleton. Dispatch GrokBot work, mine conversations, keep the principal out, never implement or push GitHub.
"""
from __future__ import annotations

from .seam_runtime import admit, stamp

DUTY = "dispatch_only"
_BLOCKED = {"implement", "push", "merge"}


def process(data: dict) -> dict:
    refused = admit("chief_of_staff", data)
    if refused:
        return refused
    action = data.get("action")
    if action in _BLOCKED:
        return {
            "ok": False,
            "error": "duty is dispatch only",
            "card": "chief_of_staff",
            "duty": DUTY,
        }
    if action is not None and not isinstance(action, str):
        return {"ok": False, "error": "action is invalid", "card": "chief_of_staff"}
    body: dict = {"duty": DUTY}
    if action is not None:
        body["action"] = action
    return stamp("chief_of_staff", data, body)
