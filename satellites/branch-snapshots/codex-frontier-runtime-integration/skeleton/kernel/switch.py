"""Switch profile and rebuild the bank."""
from __future__ import annotations

from typing import Any, Dict


def to(name: str) -> Dict[str, Any]:
    from skeleton.kernel.bank import boot, reset
    from skeleton.kernel.profiles import force

    force(str(name))
    reset()
    card = boot(str(name))
    card["switched"] = str(name)
    return card
