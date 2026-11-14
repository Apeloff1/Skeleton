"""Bounded headless operator gate for complete local GGUF campaign source output.

No inference, Git command, imported generated source or original project write
is ever performed. Inspect proves all cold private native escrows and emits
one composite source/patch/assembly digest. Publish needs those exact three
SHA-256 values and a distinct output-kind-specific CLI approval.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import BinaryIO, TextIO

from .desktop_campaign_delivery import (
    inspect_campaign_assembly, publish_campaign_assembly,
)
from .desktop_native_campaign import (
    SCHEMA as CAMPAIGN_SCHEMA, parse_campaign,
)
from .desktop_workspace import _canonical

SCHEMA = "jeeves.desktop.native-campaign-source-delivery-cli.v1"
RESULT_SCHEMA = "jeeves.desktop.native-campaign-source-delivery-result.v1"
MAX_INPUT_BYTES = 147456
MAX_OUTPUT_BYTES = 32768
_FIELDS = frozenset({
    "schema", "action", "campaign", "output_kind", "destination",
    "assembly_sha256", "source_manifest_sha256", "patch_sha256",
})


class CampaignDeliveryCLIHold(ValueError):
    """Original campaign source and manual publication authority mismatch."""


def _sha(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(
        char in "0123456789abcdef" for char in value
    )


def _pairs(items):
    obj = {}
    for key, value in items:
        if key in obj:
            raise CampaignDeliveryCLIHold("duplicate private source delivery key")
        obj[key] = value
    return obj


def _nonfinite(_):
    raise CampaignDeliveryCLIHold("nonfinite private source delivery request")


def parse_delivery_request(raw: bytes) -> dict:
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_INPUT_BYTES:
        raise CampaignDeliveryCLIHold("finite strict campaign source delivery JSON required")
    try:
        obj = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_pairs, parse_constant=_nonfinite,
        )
    except (UnicodeError, TypeError, ValueError, RecursionError) as exc:
        raise CampaignDeliveryCLIHold("malformed or ambiguous private source delivery") from exc
    if (
        type(obj) is not dict or frozenset(obj) != _FIELDS
        or obj["schema"] != SCHEMA
        or obj["action"] not in ("inspect", "publish")
        or type(obj["campaign"]) is not dict
    ):
        raise CampaignDeliveryCLIHold("unexpected source delivery authority")
    campaign, request = parse_campaign(_canonical(obj["campaign"]))
    if (
        request["schema"] != CAMPAIGN_SCHEMA
        or request["action"] != "verify"
        or not request["recheck_original_source"]
        or campaign.manifest_sha256 != request["manifest_sha256"]
    ):
        raise CampaignDeliveryCLIHold("verified completed native campaign source required")
    if obj["action"] == "inspect":
        if any(obj[k] is not None for k in (
            "output_kind", "destination", "assembly_sha256",
            "source_manifest_sha256", "patch_sha256",
        )):
            raise CampaignDeliveryCLIHold("read-only source inspection carries write grant")
    else:
        if (
            obj["output_kind"] not in ("private-stage", "git-patch")
            or type(obj["destination"]) is not str
            or not obj["destination"]
            or "\x00" in obj["destination"]
            or not Path(obj["destination"]).is_absolute()
            or ".." in Path(obj["destination"]).parts
            or any(not _sha(obj[k]) for k in (
                "assembly_sha256", "source_manifest_sha256", "patch_sha256",
            ))
        ):
            raise CampaignDeliveryCLIHold("exact full approved source bundle SHA required")
    return obj


def execute_delivery_request(
    req: dict, *, approve_private_stage: bool = False,
    approve_git_patch: bool = False,
) -> dict[str, object]:
    if (
        type(req) is not dict
        or type(approve_private_stage) is not bool
        or type(approve_git_patch) is not bool
    ):
        raise CampaignDeliveryCLIHold("strict operator source review and approval needed")
    req = parse_delivery_request(_canonical(req))
    plan, _ = parse_campaign(_canonical(req["campaign"]))
    if req["action"] == "inspect":
        if approve_private_stage or approve_git_patch:
            raise CampaignDeliveryCLIHold("cold source review cannot carry write authority")
        info = inspect_campaign_assembly(plan).public_review()
    else:
        if (
            (req["output_kind"] == "private-stage" and
             (not approve_private_stage or approve_git_patch))
            or (req["output_kind"] == "git-patch" and
                (not approve_git_patch or approve_private_stage))
        ):
            raise CampaignDeliveryCLIHold("exact distinct manual output approval required")
        info = publish_campaign_assembly(
            plan, req["destination"], output_kind=req["output_kind"],
            expected_assembly_sha256=req["assembly_sha256"],
            expected_manifest_sha256=req["source_manifest_sha256"],
            expected_patch_sha256=req["patch_sha256"],
            approve_delivery=True,
        )
    return {
        "schema": RESULT_SCHEMA,
        "action": req["action"],
        "review": info,
        "source_contents_in_stdout": False,
        "model_inference_started": False,
        "original_checkout_modified": False,
        "git_commands_executed": False,
        "release_certified": False,
    }


class _PrivateParser(argparse.ArgumentParser):
    def error(self, _message):
        raise CampaignDeliveryCLIHold("invalid manual source delivery CLI flags")


def main(
    argv: list[str] | None = None, *,
    stdin: BinaryIO | None = None, stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    parser = _PrivateParser(
        description="Cold compose real source task escrows into a reviewed private bundle",
    )
    parser.add_argument("--approve-private-stage", action="store_true")
    parser.add_argument("--approve-git-patch", action="store_true")
    input_stream = stdin if stdin is not None else sys.stdin.buffer
    output = stdout if stdout is not None else sys.stdout
    errors = stderr if stderr is not None else sys.stderr
    try:
        flags = parser.parse_args(argv)
        request = parse_delivery_request(input_stream.read(MAX_INPUT_BYTES + 1))
        result = execute_delivery_request(
            request, approve_private_stage=flags.approve_private_stage,
            approve_git_patch=flags.approve_git_patch,
        )
        encoded = _canonical(result)
        if len(encoded) > MAX_OUTPUT_BYTES:
            raise CampaignDeliveryCLIHold("public cold source bundle receipt too large")
        output.write(encoded.decode("utf-8", "strict") + "\n")
        return 0
    except (Exception, KeyboardInterrupt):
        errors.write("JEEVES_CAMPAIGN_SOURCE_DELIVERY_HELD\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "SCHEMA", "RESULT_SCHEMA", "CampaignDeliveryCLIHold",
    "parse_delivery_request", "execute_delivery_request", "main",
]
