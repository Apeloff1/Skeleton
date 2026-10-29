"""Mailbox 0003.
"""
from __future__ import annotations

BOX = "mail_0003"

def send(to: str, subject: str) -> dict:
    if not to or not subject:
        return {"ok": False, "reason": "incomplete"}
    return {"ok": True, "box": BOX, "to": to, "subject": subject[:80]}
