"""Shared mandatory architecture acknowledgement for AI provider families.

This module is intentionally dependency-light and performs no provider/network
I/O. Every credential-bearing AI provider family must obtain a receipt here
before it can perform external model I/O.

The receipt proves that:
* the active architecture and AI-construction contracts are materialized;
* every mandatory provider document was read into the digest;
* the provider is declared in the correct provider family;
* architecture/manual acknowledgement and activation receipts are required.

Provider families keep runtime model providers, automation model providers, and
other future external AI edges under one contract without making backend code
the owner of repository-wide policy.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any


class ProviderArchitectureError(RuntimeError):
    """Provider activation cannot satisfy the mandatory architecture contract."""


@dataclass(frozen=True, slots=True)
class ProviderArchitectureReceipt:
    """Non-secret evidence that a provider loaded the active construction contract."""

    provider_id: str
    architecture_tag: str
    construction_version: str
    contract_digest: str
    manual_path: str
    required_documents: tuple[str, ...]
    provider_family: str = "runtime_model"

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "provider_family": self.provider_family,
            "architecture_tag": self.architecture_tag,
            "construction_version": self.construction_version,
            "contract_digest": self.contract_digest,
            "manual_path": self.manual_path,
            "required_documents": list(self.required_documents),
        }


def _read_json(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ProviderArchitectureError(
            f"mandatory provider contract is unavailable: {path}"
        ) from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProviderArchitectureError(
            f"mandatory provider contract is invalid JSON: {path}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProviderArchitectureError(
            f"mandatory provider contract must be an object: {path}"
        )
    return payload, raw


def _candidate_roots(explicit: str | Path | None) -> list[Path]:
    roots: list[Path] = []
    if explicit is not None:
        roots.append(Path(explicit))
    configured = os.getenv("AI_ARCHITECTURE_ROOT", "").strip()
    if configured:
        roots.append(Path(configured))
    roots.append(Path.cwd())

    here = Path(__file__).resolve()
    roots.extend(here.parents)

    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in roots:
        resolved = candidate.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def locate_contract_root(explicit: str | Path | None = None) -> Path:
    """Find the materialized construction root without consulting the network.

    An explicit root is authoritative: if it is incomplete, activation fails
    closed instead of silently falling back to another checkout.
    """

    if explicit is not None:
        root = Path(explicit).resolve()
        if (
            (root / "machine/manifest.json").is_file()
            and (root / "machine/architecture.json").is_file()
            and (root / "machine/ai_app_construction.json").is_file()
            and (root / "docs/AI_APP_CONSTRUCTION_MANUAL.md").is_file()
        ):
            return root
        raise ProviderArchitectureError(
            "mandatory AI architecture contracts are not materialized at explicit root"
        )

    for root in _candidate_roots(None):
        if (
            (root / "machine/manifest.json").is_file()
            and (root / "machine/architecture.json").is_file()
            and (root / "machine/ai_app_construction.json").is_file()
            and (root / "docs/AI_APP_CONSTRUCTION_MANUAL.md").is_file()
        ):
            return root
    raise ProviderArchitectureError(
        "mandatory AI architecture contracts are not materialized; "
        "set AI_ARCHITECTURE_ROOT or package machine/ and docs/ with the runtime"
    )


def _provider_list_name(provider_family: str) -> str:
    normalized = provider_family.strip().lower().replace("-", "_")
    mapping = {
        "runtime_model": "runtime_model_providers",
        "automation_model": "automation_model_providers",
    }
    try:
        return mapping[normalized]
    except KeyError as exc:
        raise ProviderArchitectureError(
            f"unknown provider family: {provider_family!r}"
        ) from exc


def load_provider_architecture(
    provider_id: str,
    *,
    provider_family: str = "runtime_model",
    root: str | Path | None = None,
) -> ProviderArchitectureReceipt:
    """Load and validate mandatory construction documents for one provider."""

    normalized = str(provider_id).strip().lower()
    family = str(provider_family).strip().lower().replace("-", "_")
    if not normalized:
        raise ProviderArchitectureError(
            "provider id is required for architecture acknowledgement"
        )

    contract_root = locate_contract_root(root)
    architecture, architecture_raw = _read_json(
        contract_root / "machine/architecture.json"
    )
    construction, construction_raw = _read_json(
        contract_root / "machine/ai_app_construction.json"
    )

    if architecture.get("status") != "active":
        raise ProviderArchitectureError("architecture contract is not active")
    if construction.get("status") != "active":
        raise ProviderArchitectureError("AI construction contract is not active")

    architecture_tag = architecture.get("architecture_tag")
    if not isinstance(architecture_tag, str) or not architecture_tag:
        raise ProviderArchitectureError("architecture tag is missing")
    if construction.get("architecture_tag") != architecture_tag:
        raise ProviderArchitectureError(
            "AI construction contract architecture tag does not match active architecture"
        )

    bootstrap = construction.get("provider_bootstrap")
    if not isinstance(bootstrap, dict):
        raise ProviderArchitectureError("provider bootstrap contract is missing")
    if bootstrap.get("mandatory") is not True or bootstrap.get("mode") != "fail_closed":
        raise ProviderArchitectureError(
            "provider bootstrap must be mandatory and fail-closed"
        )

    required_documents = bootstrap.get("must_read")
    if not isinstance(required_documents, list) or not required_documents:
        raise ProviderArchitectureError(
            "provider bootstrap must declare required documents"
        )

    digest = hashlib.sha256()
    digest.update(architecture_raw)
    digest.update(construction_raw)
    normalized_documents: list[str] = []
    for relative in required_documents:
        if not isinstance(relative, str) or not relative:
            raise ProviderArchitectureError(
                "provider bootstrap contains an invalid document path"
            )
        path = contract_root / relative
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise ProviderArchitectureError(
                f"mandatory provider document is unavailable: {relative}"
            ) from exc
        if not raw.strip():
            raise ProviderArchitectureError(
                f"mandatory provider document is empty: {relative}"
            )
        digest.update(relative.encode("utf-8"))
        digest.update(raw)
        normalized_documents.append(relative)

    declaration_key = _provider_list_name(family)
    declared = construction.get(declaration_key)
    if not isinstance(declared, list):
        raise ProviderArchitectureError(f"{declaration_key} must be a list")
    declaration = next(
        (
            item
            for item in declared
            if isinstance(item, dict)
            and str(item.get("id", "")).strip().lower() == normalized
        ),
        None,
    )
    if declaration is None:
        raise ProviderArchitectureError(
            f"AI provider is not declared in {declaration_key}: {normalized}"
        )
    for key in (
        "architecture_read_required",
        "construction_manual_read_required",
        "activation_receipt_required",
    ):
        if declaration.get(key) is not True:
            raise ProviderArchitectureError(
                f"provider {normalized} does not require {key}"
            )

    construction_version = construction.get("construction_version")
    if not isinstance(construction_version, str) or not construction_version:
        raise ProviderArchitectureError("construction version is missing")

    manual_path = construction.get("human_manual")
    if not isinstance(manual_path, str) or not manual_path:
        raise ProviderArchitectureError("construction human manual path is missing")
    if manual_path not in normalized_documents:
        raise ProviderArchitectureError(
            "construction manual must be included in mandatory provider documents"
        )

    return ProviderArchitectureReceipt(
        provider_id=normalized,
        provider_family=family,
        architecture_tag=architecture_tag,
        construction_version=construction_version,
        contract_digest=digest.hexdigest(),
        manual_path=manual_path,
        required_documents=tuple(normalized_documents),
    )


__all__ = [
    "ProviderArchitectureError",
    "ProviderArchitectureReceipt",
    "load_provider_architecture",
    "locate_contract_root",
]
