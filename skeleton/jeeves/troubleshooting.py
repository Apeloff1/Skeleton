"""Troubleshooting — guide a stuck tutoring session.

Assessment can mark a session "stuck" when mastery stalls; troubleshooting
takes that session, runs a fixed playbook (read instructions, attempt
simplification, cross-check examples), and proposes the next hint.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Tuple

from skeleton.jeeves.pedagogy import Scaffold


@dataclass(frozen=True)
class TroubleshootingStep:
    name: str
    action: Callable[[Scaffold], None]


class Troubleshooter:
    """Linear playbook runner; returns the step to try next."""

    STEPS: Tuple[Tuple[str, str], ...] = (
        ("read-instructions", "Re-read task requirements"),
        ("simplify", "Try with smaller data/parameter space"),
        ("find-example", "Look for a worked example"),
        ("escalate", "Request explicit guidance"),
    )

    def next_step(self, scaffold: Scaffold) -> Optional[Tuple[str, str]]:
        undertaken = {getattr(h, "payload", {}).get("step") for h in scaffold.used}
        for name, text in self.STEPS:
            if name not in undertaken:
                return (name, text)
        return None

    def diagnose(self, scaffold: Scaffold) -> Tuple[str, str]:
        step = self.next_step(scaffold)
        if step is None:
            return ("attempts-complete", "review the trajectory")
        return step
