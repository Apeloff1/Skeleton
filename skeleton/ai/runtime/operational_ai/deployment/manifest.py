"""Machine-readable stage ownership and locally measured qualification inventory."""
from __future__ import annotations
from pathlib import Path
from ..authority.canonical import ContractViolation,digest

STAGES={
    "MBW-00":["authority"],
    "MBW-01":["persistence"],
    "MBW-02":["model","context"],
    "MBW-03":["tools"],
    "MBW-04":["orchestration"],
    "MBW-05":["transport"],
    "MBW-06":["evaluation"],
    "MBW-07":["deployment"],
}

def inventory(root:Path)->dict:
    expected=Path(__file__).resolve().parents[1]
    if root.resolve()!=expected:
        raise ContractViolation("inventory must use canonical operational AI root")
    counts={}
    for wave,branches in STAGES.items():
        count=0
        for branch in branches:
            count+=sum(1 for file in (root/branch).glob("*.py") if file.is_file() and not file.is_symlink())
        counts[wave]=count
    return {"schema":"skeleton.operational-ai.inventory.v1","waves":counts,
            "status":"source-inventory-not-completion-proof","digest":digest(counts)}
