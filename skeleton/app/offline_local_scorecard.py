"""Measured local gates and the enterprise census they do not promote.

Running these gates records what this process actually did. An untrained
native checkpoint stays unqualified. The 421 masterplan volumes stay at the
grade already stored in the enterprise contract. This module does not write
that contract and does not invent quality scores.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from typing import Any
from uuid import uuid4

from skeleton.app.offline_background_job import LocalReferenceJob
from skeleton.app.offline_knowledge import OfflineKnowledgeLibrary
from skeleton.app.offline_reference_read import LocalReferenceRead
from skeleton.app.offline_reference_write import LocalReferenceWrite
from skeleton.ai.model_runtime.offline_chat import OfflineChatStore
from skeleton.cortex.transformer import TinyTransformer
from skeleton.intelligence.background_agent import READ_TOOLS, WRITE_TOOLS
from skeleton.intelligence.grounded_journey import assess_supplied_passages


SCHEMA = "skeleton.app.offline_local_scorecard.v1"
_ROOT = Path(__file__).resolve().parents[2]
_HEAD = re.compile(r"[0-9a-f]{40}")
_PASSAGE = {
    "citation": "local:scorecard",
    "title": "Mode note",
    "passage": "The mode is enabled.",
}


def _faithfulness() -> dict[str, Any]:
    supported = assess_supplied_passages("The mode is enabled.", [_PASSAGE])
    withheld = assess_supplied_passages("The mode is quantum.", [_PASSAGE])
    if supported["disposition"] != "supported":
        raise RuntimeError("faithfulness gate did not publish a supported sentence")
    if withheld["disposition"] != "abstain" or "quantum" in withheld["published_text"]:
        raise RuntimeError("faithfulness gate published an unsupported sentence")
    return {
        "passed": True,
        "method": supported["method"],
        "supported_disposition": supported["disposition"],
        "unsupported_disposition": withheld["disposition"],
    }


def _tools(library: OfflineKnowledgeLibrary) -> dict[str, Any]:
    library.add_text("Mode note", "The mode is enabled.")
    reader = LocalReferenceRead(library)
    read = reader.read("mode enabled", str(uuid4()), granted=True)
    if read["status"] != "succeeded" or not read["hits"]:
        raise RuntimeError("reference read gate did not return the stored passage")
    writer = LocalReferenceWrite(library)
    request_id = str(uuid4())
    waiting = writer.write(
        "Depth note",
        "The depth buffer stores a depth value for each pixel.",
        request_id,
        approved=True,
    )
    if waiting["error_code"] != "approval_required" or waiting["written"] is not False:
        raise RuntimeError("reference write gate wrote before approval")
    if library.search("depth buffer"):
        raise RuntimeError("unapproved reference write changed the library")
    written = writer.write(
        "Depth note",
        "The depth buffer stores a depth value for each pixel.",
        request_id,
        approved=True,
        approval_ref=waiting["expected_approval_ref"],
    )
    if written["status"] != "succeeded" or written["created"] is not True:
        raise RuntimeError("approved reference write did not create a document")
    if not library.search("depth buffer"):
        raise RuntimeError("approved reference write is not searchable")
    rolled = writer.rollback(request_id, approved=True)
    if rolled["rolled_back"] is not True or library.search("depth buffer"):
        raise RuntimeError("reference write rollback left the document in place")
    return {
        "reference_read": {"passed": True, "tool_id": read["tool_id"]},
        "reference_write_approval": {"passed": True, "tool_id": written["tool_id"]},
        "reference_write_rollback": {"passed": True, "document_id": rolled["document_id"]},
    }


def _job(library: OfflineKnowledgeLibrary) -> dict[str, Any]:
    job = LocalReferenceJob(library)
    blocked = job.run(
        "mode enabled",
        str(uuid4()),
        granted=True,
        allow_writes=False,
        title="Should not land",
        text="This write must not land in the library.",
    )
    if blocked["status"] != "blocked" or blocked["steps"] != 0:
        raise RuntimeError("background job executed a write that was not allowed")
    if "local.reference.read" not in READ_TOOLS or "local.reference.write" not in WRITE_TOOLS:
        raise RuntimeError("local reference tools are outside the background agent allow profile")
    ran = job.run("mode enabled", str(uuid4()), granted=True, allow_writes=False)
    if ran["status"] != "completed" or ran["calls"] != ["local.reference.read"]:
        raise RuntimeError("background job did not complete the bounded read")
    if ran["max_steps"] > 2 or ran["max_children"] != 0:
        raise RuntimeError("background job exceeded its bound")
    return {
        "passed": True,
        "read_calls": ran["calls"],
        "write_blocked_before_execution": True,
        "max_steps": ran["max_steps"],
        "max_children": ran["max_children"],
    }


def _untrained_transport() -> dict[str, Any]:
    model = TinyTransformer(
        vocab=("the", "mode", "is", "enabled"),
        dim=8, ctx=8, seed=1, n_heads=2, n_layers=1, d_ff=16,
    )
    first = model.generate("the", n=2, seed=1)
    second = model.generate("the", n=2, seed=1)
    if first != second or len(first) != 2:
        raise RuntimeError("untrained transport generation was not deterministic")
    digest = sha256("\n".join(first).encode("utf-8")).hexdigest()
    return {
        "runtime": "TinyTransformer",
        "trained": False,
        "quality_state": "unqualified",
        "reason": "untrained_transport_only",
        "tokens_generated": 2,
        "output_sha256": digest,
        "scores": None,
    }


def _enterprise(root: Path) -> dict[str, Any]:
    policy = json.loads((root / "machine" / "enterprise_ai_superiority.json").read_text(encoding="utf-8"))
    master = json.loads((root / "machine" / "ai_master_plan.json").read_text(encoding="utf-8"))
    profiles = policy["profiles"]
    volumes = master["volumes"]
    grade_counts: dict[str, int] = {}
    qualified_volumes = 0
    for volume in volumes:
        state = volume.get("enterprise_grade_state")
        grade_counts[str(state)] = grade_counts.get(str(state), 0) + 1
        if state in {"enterprise_qualified", "superior"}:
            qualified_volumes += 1
    profile_counts: dict[str, int] = {}
    superior_profiles = 0
    for profile in profiles:
        state = profile.get("qualification_state")
        profile_counts[str(state)] = profile_counts.get(str(state), 0) + 1
        if state == "superior":
            superior_profiles += 1
    complete = (
        len(volumes) == 421
        and qualified_volumes == len(volumes)
        and len(profiles) > 0
        and superior_profiles == len(profiles)
    )
    return {
        "volume_count": len(volumes),
        "volumes_enterprise_qualified_or_superior": qualified_volumes,
        "master_grade_counts": grade_counts,
        "profile_count": len(profiles),
        "profile_qualification_counts": profile_counts,
        "profile_superior": superior_profiles,
        "complete_claim_satisfied": complete,
        "promotion_performed": False,
        "reason": (
            "exact-head enterprise qualification evidence was not produced for "
            "VOL-000 through VOL-420"
        ),
    }


def measure_local_system(*, head: str | None, root: Path | None = None) -> dict[str, Any]:
    """Run the local gates and census the enterprise contract without promoting it."""

    identity = head if isinstance(head, str) else ""
    with TemporaryDirectory(prefix="skeleton-local-scorecard-") as scratch:
        store = OfflineChatStore(Path(scratch) / "scorecard.sqlite3")
        try:
            library = OfflineKnowledgeLibrary(store, "a" * 64, "b" * 64)
            tools = _tools(library)
            job = _job(library)
        finally:
            store.close()
    census = _enterprise(root or _ROOT)
    return {
        "schema": SCHEMA,
        "head": identity or "head_not_supplied",
        "exact_head": _HEAD.fullmatch(identity) is not None,
        "gates": {
            "claim_faithfulness": _faithfulness(),
            **tools,
            "background_job": job,
        },
        "trained_model_quality": _untrained_transport(),
        "enterprise": census,
    }
