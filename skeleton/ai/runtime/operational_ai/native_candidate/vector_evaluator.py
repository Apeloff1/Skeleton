"""Evaluate input-boundary vectors against executable candidate contracts."""
from __future__ import annotations
from dataclasses import replace
import json

from .catalog import iter_examples
from .candidate_authority import AuthorityAssignment
from .dedup import require_unique
from .errors import CandidateRejected, deny
from .plan import TrainingPlan
from .privacy import inspect_public_record
from .records import TrainingExample
from .run_limits import ResourceLimits
from .semantic_oracle import verify
from .splits import partition
from .state_rules import RunState
from .strict import decode, identity, sha


def evaluate(domain: str, arg: dict) -> dict:
    try:
        if domain == "canonical":
            decode(arg["value"])
        elif domain == "identity":
            identity(arg["value"])
        elif domain == "rights":
            row = next(iter_examples()).record()
            row.update(arg["changes"])
            TrainingExample.parse(json.dumps(row).encode("utf-8"))
        elif domain == "dedup":
            source_rows = tuple(iter_examples())
            start = arg["offset"]
            rows = source_rows[start:start+2]
            if arg["duplicate"]:
                rows = (rows[0], replace(rows[1], prompt=rows[0].prompt))
            require_unique(rows)
        elif domain == "split":
            rows = list(iter_examples())
            index = arg["offset"]
            if arg["mode"] == "missing":
                rows.pop(index)
            elif arg["mode"] == "duplicate":
                rows[index+1] = replace(rows[index+1], group_id=rows[index].group_id)
            elif arg["mode"] == "cross":
                rows[-1] = replace(rows[-1], group_id=rows[index].group_id)
            elif arg["mode"] != "clean":
                deny("split-mode")
            partition(tuple(rows))
        elif domain == "plan":
            TrainingPlan(
                arg["run_id"], "a"*64, "b"*64,
                learning_rate_ppm=arg["learning_rate_ppm"],
                max_optimizer_steps=arg["steps"],
                batch_lines=arg["batch_lines"],
                operator_approved=arg["approved"],
            )
        elif domain == "state":
            RunState("run_1", arg["from"]).advance(arg["to"])
        elif domain == "roles":
            AuthorityAssignment(*arg["actors"])
        elif domain == "privacy":
            if not inspect_public_record(arg["record"])["publishable"]:
                deny("private-fields")
        elif domain == "source_truth":
            source = tuple(iter_examples())[arg["offset"]]
            if arg["modified"]:
                source = replace(source, completion=source.completion + "_wrong")
            if not verify(source):
                deny("source-truth")
        elif domain == "resource":
            ResourceLimits().admit(
                model_bytes=arg["model_bytes"], steps=arg["steps"],
                examples=arg["examples"], estimated_working_bytes=arg["working_bytes"]
            )
        elif domain == "digest":
            sha(arg["value"])
        else:
            deny("vector-domain")
        return {"allowed": True, "code": "admitted"}
    except CandidateRejected as exc:
        return {"allowed": False, "code": exc.code}
