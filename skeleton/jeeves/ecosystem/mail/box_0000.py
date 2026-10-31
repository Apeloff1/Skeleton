"""Mailbox 0000.
"""
from __future__ import annotations

BOX = "mail_0000"

def send(to: str, subject: str) -> dict:
    if not to or not subject:
        return {"ok": False, "reason": "incomplete"}
    return {"ok": True, "box": BOX, "to": to, "subject": subject[:80]}
