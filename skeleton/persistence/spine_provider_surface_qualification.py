"""Paired exact-head provider-surface closure qualification."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


class SpineProviderSurfaceQualificationError(RuntimeError):
    """Provider-surface closure evidence failed closed."""


_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_CORE_FIELDS = (
    "id",
    "owner",
    "surface_class",
    "credential_owner",
    "network_transport_owner",
    "sdk_client_owner",
)


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _head(value: object) -> str:
    if not isinstance(value, str) or _SHA_RE.fullmatch(value) is None:
        raise SpineProviderSurfaceQualificationError(
            "provider receipt head SHA is invalid"
        )
    return value


def _core_declared(rows: object) -> list[dict[str, Any]]:
    if not isinstance(rows, list) or not rows:
        raise SpineProviderSurfaceQualificationError(
            "provider declared surfaces are missing"
        )
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise SpineProviderSurfaceQualificationError(
                "provider declared surface must be an object"
            )
        item = {field: row.get(field) for field in _CORE_FIELDS}
        if not isinstance(item["id"], str) or not item["id"]:
            raise SpineProviderSurfaceQualificationError(
                "provider declared surface id is invalid"
            )
        if not isinstance(item["owner"], str) or not item["owner"]:
            raise SpineProviderSurfaceQualificationError(
                "provider declared surface owner is invalid"
            )
        normalized.append(item)
    return sorted(
        normalized,
        key=lambda item: (str(item["id"]), str(item["owner"])),
    )


def _edge_rows_from_canonical(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, dict) or not value:
        raise SpineProviderSurfaceQualificationError(
            "canonical discovered provider surfaces are missing"
        )
    rows: list[dict[str, Any]] = []
    for path, evidence in value.items():
        if not isinstance(path, str) or not path:
            raise SpineProviderSurfaceQualificationError(
                "canonical provider path is invalid"
            )
        if not isinstance(evidence, dict):
            raise SpineProviderSurfaceQualificationError(
                "canonical provider edge evidence must be an object"
            )
        edge_classes = evidence.get("edge_classes")
        if not isinstance(edge_classes, list) or not edge_classes:
            raise SpineProviderSurfaceQualificationError(
                "canonical provider edge classes are missing"
            )
        rows.append(
            {
                "path": path,
                "edge_classes": sorted(str(item) for item in edge_classes),
            }
        )
    return sorted(rows, key=lambda item: item["path"])


def _edge_rows_from_independent(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise SpineProviderSurfaceQualificationError(
            "independent discovered provider edges are missing"
        )
    rows: list[dict[str, Any]] = []
    for evidence in value:
        if not isinstance(evidence, dict):
            raise SpineProviderSurfaceQualificationError(
                "independent provider edge evidence must be an object"
            )
        path = evidence.get("path")
        edge_classes = evidence.get("edge_classes")
        if not isinstance(path, str) or not path:
            raise SpineProviderSurfaceQualificationError(
                "independent provider path is invalid"
            )
        if not isinstance(edge_classes, list) or not edge_classes:
            raise SpineProviderSurfaceQualificationError(
                "independent provider edge classes are missing"
            )
        rows.append(
            {
                "path": path,
                "edge_classes": sorted(str(item) for item in edge_classes),
            }
        )
    return sorted(rows, key=lambda item: item["path"])


class SpineProviderSurfaceQualification:
    """Normalize two provider closure receipts and require exact agreement."""

    @staticmethod
    def canonical_summary(receipt: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(receipt, dict) or receipt.get("schema_version") != 1:
            raise SpineProviderSurfaceQualificationError(
                "canonical provider receipt schema is invalid"
            )
        if receipt.get("valid") is not True or receipt.get("validation_errors"):
            raise SpineProviderSurfaceQualificationError(
                "canonical provider receipt is not valid"
            )
        head_sha = _head(receipt.get("head_sha"))
        declared = _core_declared(receipt.get("declared_surfaces"))
        edges = _edge_rows_from_canonical(receipt.get("discovered_surfaces"))
        return {
            "kind": "spine_provider_surface_canonical_summary",
            "head_sha": head_sha,
            "declared_digest": _digest(declared),
            "discovered_digest": _digest(edges),
            "declared_count": len(declared),
            "discovered_count": len(edges),
            "receipt_digest": _digest(receipt),
        }

    @staticmethod
    def independent_summary(receipt: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(receipt, dict) or receipt.get("schema_version") != 1:
            raise SpineProviderSurfaceQualificationError(
                "independent provider receipt schema is invalid"
            )
        if receipt.get("verifier") != "independent-provider-surface-v1":
            raise SpineProviderSurfaceQualificationError(
                "independent provider verifier identity changed"
            )
        if receipt.get("valid") is not True or receipt.get("errors"):
            raise SpineProviderSurfaceQualificationError(
                "independent provider receipt is not valid"
            )
        scanned = receipt.get("scanned_python_files")
        if isinstance(scanned, bool) or not isinstance(scanned, int) or scanned < 1:
            raise SpineProviderSurfaceQualificationError(
                "independent provider scan covered no Python files"
            )
        declared_surface_digest = receipt.get("declared_surface_digest")
        if (
            not isinstance(declared_surface_digest, str)
            or _DIGEST_RE.fullmatch(declared_surface_digest) is None
        ):
            raise SpineProviderSurfaceQualificationError(
                "independent declaration digest is invalid"
            )
        head_sha = _head(receipt.get("head_sha"))
        declared = _core_declared(receipt.get("declared_surfaces"))
        edges = _edge_rows_from_independent(
            receipt.get("discovered_provider_edges")
        )
        return {
            "kind": "spine_provider_surface_independent_summary",
            "head_sha": head_sha,
            "declared_digest": _digest(declared),
            "discovered_digest": _digest(edges),
            "declared_count": len(declared),
            "discovered_count": len(edges),
            "scanned_python_files": scanned,
            "declared_surface_digest": declared_surface_digest,
            "receipt_digest": _digest(receipt),
        }

    def qualify(
        self,
        *,
        canonical: dict[str, Any],
        independent: dict[str, Any],
        expected_head_sha: str,
    ) -> dict[str, Any]:
        expected = _head(expected_head_sha)
        if (
            not isinstance(canonical, dict)
            or canonical.get("kind")
            != "spine_provider_surface_canonical_summary"
        ):
            raise SpineProviderSurfaceQualificationError(
                "canonical provider summary is required"
            )
        if (
            not isinstance(independent, dict)
            or independent.get("kind")
            != "spine_provider_surface_independent_summary"
        ):
            raise SpineProviderSurfaceQualificationError(
                "independent provider summary is required"
            )
        if canonical.get("head_sha") != expected:
            raise SpineProviderSurfaceQualificationError(
                "canonical provider summary is not exact-head"
            )
        if independent.get("head_sha") != expected:
            raise SpineProviderSurfaceQualificationError(
                "independent provider summary is not exact-head"
            )
        for field in ("declared_digest", "discovered_digest"):
            left = canonical.get(field)
            right = independent.get(field)
            if (
                not isinstance(left, str)
                or _DIGEST_RE.fullmatch(left) is None
                or left != right
            ):
                raise SpineProviderSurfaceQualificationError(
                    f"provider summaries disagree on {field}"
                )
        for field in ("declared_count", "discovered_count"):
            left = canonical.get(field)
            right = independent.get(field)
            if (
                isinstance(left, bool)
                or not isinstance(left, int)
                or left < 1
                or left != right
            ):
                raise SpineProviderSurfaceQualificationError(
                    f"provider summaries disagree on {field}"
                )
        for summary in (canonical, independent):
            digest = summary.get("receipt_digest")
            if (
                not isinstance(digest, str)
                or _DIGEST_RE.fullmatch(digest) is None
            ):
                raise SpineProviderSurfaceQualificationError(
                    "provider receipt digest is invalid"
                )

        evidence = {
            "head_sha": expected,
            "canonical_receipt_digest": canonical["receipt_digest"],
            "independent_receipt_digest": independent["receipt_digest"],
            "declared_digest": canonical["declared_digest"],
            "independent_declared_surface_digest": independent[
                "declared_surface_digest"
            ],
            "discovered_digest": canonical["discovered_digest"],
            "declared_count": canonical["declared_count"],
            "discovered_count": canonical["discovered_count"],
            "scanned_python_files": independent["scanned_python_files"],
            "exact_head": True,
            "independent_agreement": True,
            "provider_surface_closure_green": True,
            "provider_surface_live_green": False,
            "provider_surface_green": False,
            "pr_automation_green": False,
        }
        return {
            "kind": "spine_provider_surface_qualification",
            "hit": True,
            "law": "paired-exact-head-receipts-qualify-provider-closure",
            "citation": "VOL-134",
            **evidence,
            "digest": _digest(evidence),
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
