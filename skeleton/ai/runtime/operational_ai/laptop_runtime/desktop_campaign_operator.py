"""RAM-only operator session for inspected native Jeeves coding campaigns.

A GUI or other local controller must NOT substitute its own approvals for the
existing native/SQLite/private-artifact authorities. This class only pins the
canonical original review request, checks full manually typed digests, and
routes all model effects through the existing original engine functions.
It deliberately has no hidden resume, background retry or source-write grant.
"""
from __future__ import annotations

from hashlib import sha256
from typing import Callable

from .desktop_native_campaign import (
    SCHEMA as CAMPAIGN_SCHEMA, parse_campaign,
    execute_campaign_request,
)
from .desktop_campaign_delivery_cli import (
    SCHEMA as DELIVERY_SCHEMA, execute_delivery_request,
)
from .desktop_workspace import _canonical


class NativeCampaignOperatorHold(ValueError):
    """Source campaign operator has no current exact consent or approved work."""


def _sha(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(
        c in "0123456789abcdef" for c in value
    )


class NativeCampaignOperator:
    """One operator's RAM-only cold-review/launch/custody control surface."""

    def __init__(self):
        self._request: dict | None = None
        self._fingerprint: str | None = None
        self._manifest: str | None = None
        self._run_started = False
        self._published = False
        self._assembly: dict | None = None
        self._assembly_fingerprint: str | None = None

    @property
    def approved_manifest(self) -> str | None:
        return self._manifest

    @property
    def native_launch_consumed(self) -> bool:
        return self._run_started

    def reset(self) -> None:
        """Discard RAM approval. Never reset SQLite/journal/native work."""
        self._request = None
        self._fingerprint = self._manifest = None
        self._assembly = None
        self._assembly_fingerprint = None
        self._run_started = False
        self._published = False

    def _parse_original(self, raw: bytes):
        plan, request = parse_campaign(raw)
        if request["schema"] != CAMPAIGN_SCHEMA or request["action"] != "inspect":
            raise NativeCampaignOperatorHold("paste an original read-only campaign inspection")
        return plan, request

    def _fence(self, raw: bytes) -> tuple[dict, str]:
        if (
            self._request is None or self._manifest is None
            or self._fingerprint is None
        ):
            raise NativeCampaignOperatorHold("inspect original native source first")
        _, request = self._parse_original(raw)
        fingerprint = sha256(_canonical(request)).hexdigest()
        if fingerprint != self._fingerprint:
            raise NativeCampaignOperatorHold("original inspected task bytes changed")
        return request, fingerprint

    def inspect(self, raw: bytes) -> dict[str, object]:
        if self._run_started:
            raise NativeCampaignOperatorHold(
                "a native launch already began; cannot rearm it in this workbench",
            )
        _, request = self._parse_original(raw)
        preview = execute_campaign_request(request)
        if (
            preview.get("status") != "review-required-before-original-native-campaign"
            or not _sha(preview.get("manifest_sha256"))
        ):
            raise NativeCampaignOperatorHold("original source campaign inspection not qualified")
        self._request = request
        self._fingerprint = sha256(_canonical(request)).hexdigest()
        self._manifest = preview["manifest_sha256"]
        self._assembly = None
        self._assembly_fingerprint = None
        return preview

    def _verified_request(self, raw: bytes, *, recheck_original: bool) -> dict:
        req, _ = self._fence(raw)
        return {
            **req, "action": "verify",
            "manifest_sha256": self._manifest,
            "recheck_original_source": recheck_original,
        }

    def run(
        self, raw: bytes, *, typed_manifest_sha256: str,
        approve_campaign: bool, approve_native: bool,
        approve_private_storage: bool,
        bridge_factory: Callable | None = None,
    ) -> dict[str, object]:
        request, _ = self._fence(raw)
        if self._run_started:
            raise NativeCampaignOperatorHold("native campaign already attempted in this session")
        if (
            not _sha(typed_manifest_sha256)
            or typed_manifest_sha256 != self._manifest
            or any(x is not True for x in (
                approve_campaign, approve_native, approve_private_storage,
            ))
        ):
            raise NativeCampaignOperatorHold("three distinct operator approvals and full typed SHA required")
        self._run_started = True
        args = {
            "approve_campaign": True, "approve_native": True,
            "approve_private_storage": True,
        }
        if bridge_factory is not None:
            args["bridge_factory"] = bridge_factory
        # This is intentionally ONE invocation. Unknown exceptions never
        # rearm the campaign, even if no output file was observed.
        return execute_campaign_request({
            **request, "action": "run",
            "manifest_sha256": self._manifest,
            "recheck_original_source": False,
        }, **args)

    def verify(self, raw: bytes, *, recheck_original: bool) -> dict[str, object]:
        if type(recheck_original) is not bool:
            raise NativeCampaignOperatorHold("explicit cold original source flag required")
        return execute_campaign_request(
            self._verified_request(raw, recheck_original=recheck_original),
        )

    def inspect_assembly(self, raw: bytes) -> dict[str, object]:
        _, fingerprint = self._fence(raw)
        request = {
            "schema": DELIVERY_SCHEMA, "action": "inspect",
            "campaign": self._verified_request(raw, recheck_original=True),
            "output_kind": None, "destination": None,
            "assembly_sha256": None,
            "source_manifest_sha256": None, "patch_sha256": None,
        }
        result = execute_delivery_request(request)
        body = result.get("review", {})
        if (
            type(body) is not dict
            or body.get("status") != "combined-native-source-reviewed-no-write"
            or any(not _sha(body.get(key)) for key in (
                "assembly_sha256", "combined_source_manifest_sha256",
                "combined_patch_sha256",
            ))
        ):
            raise NativeCampaignOperatorHold("combined source assembly not cold-verified")
        self._assembly = body
        self._assembly_fingerprint = fingerprint
        return body

    def publish(
        self, raw: bytes, *,
        destination: str, output_kind: str,
        assembly_sha256: str, source_manifest_sha256: str,
        patch_sha256: str, approve_private_stage: bool,
        approve_git_patch: bool,
    ) -> dict[str, object]:
        _, fingerprint = self._fence(raw)
        if (
            self._published or self._assembly is None
            or fingerprint != self._assembly_fingerprint
            or not (
                (output_kind == "git-patch" and
                 approve_git_patch is True and approve_private_stage is False)
                or (output_kind == "private-stage" and
                    approve_private_stage is True and approve_git_patch is False)
            )
            or assembly_sha256 != self._assembly.get("assembly_sha256")
            or source_manifest_sha256 != self._assembly.get(
                "combined_source_manifest_sha256",
            )
            or patch_sha256 != self._assembly.get("combined_patch_sha256")
        ):
            raise NativeCampaignOperatorHold("full fresh reviewed source digest and distinct approval required")
        self._published = True
        return execute_delivery_request({
            "schema": DELIVERY_SCHEMA, "action": "publish",
            "campaign": self._verified_request(raw, recheck_original=True),
            "output_kind": output_kind, "destination": destination,
            "assembly_sha256": assembly_sha256,
            "source_manifest_sha256": source_manifest_sha256,
            "patch_sha256": patch_sha256,
        }, approve_private_stage=approve_private_stage,
           approve_git_patch=approve_git_patch)


__all__ = ["NativeCampaignOperatorHold", "NativeCampaignOperator"]
