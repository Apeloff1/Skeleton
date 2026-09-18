#!/usr/bin/env python3
"""Provider-neutral fail-closed capability matrix (#969 S051).

Conflict domain: ``ai.spec.provider_capabilities``. This is a declaration
schema, not model routing. Unknown capability remains unknown and is never
guessed from aliases, sibling capabilities, missing rows, or vendor names.

Finding prefix: ``provider-capability``. Distinct from #1036 model
selection/routing; this module never ranks, scores, or selects models.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Mapping, Sequence


SCHEMA_VERSION = 1
TASK_KEY = "reserve-S051-provider-capability-matrix"
CONFLICT_DOMAIN = "ai.spec.provider_capabilities"
KNOWN_CAPABILITIES: tuple[str, ...] = (
    "chat",
    "tools",
    "streaming",
    "embeddings",
    "structured_output",
    "vision",
    "audio",
)
KNOWN_CAPABILITY_SET = frozenset(KNOWN_CAPABILITIES)
STATUSES: tuple[str, ...] = ("supported", "unsupported", "unknown")
STATUS_SET = frozenset(STATUSES)
GUESSED_STATUSES = frozenset(
    {
        "likely",
        "assumed",
        "inferred",
        "probably",
        "maybe",
        "yes",
        "no",
        "true",
        "false",
        "partial",
        "experimental",
    }
)
VENDOR_ALIASES = frozenset(
    {
        "function_calling",
        "json_mode",
        "json_object",
        "response_format",
        "images",
        "image_input",
        "speech",
        "whisper",
        "completions",
        "chat_completions",
    }
)
ROUTING_FIELDS = frozenset(
    {
        "selected_model",
        "fallback_model",
        "candidate_models",
        "route",
        "rank",
        "score",
        "routing_score",
        "routing_policy",
        "fallback",
    }
)
DOCUMENT_FIELDS = frozenset({"schema_version", "providers"})
PROVIDER_FIELDS = frozenset({"provider_id", "capabilities"})
CAPABILITY_FIELDS = frozenset({"name", "status", "evidence_refs"})
_FINDING_PREFIX = "provider-capability"


def _error(code: str, message: str) -> str:
    return f"{_FINDING_PREFIX} {code}: {message}"


def _reject_routing_fields(payload: Mapping[object, object], loc: str, errors: list[str]) -> None:
    overlap = set(payload) & ROUTING_FIELDS
    if overlap:
        errors.append(
            _error(
                "unknown routing_field",
                f"{loc} mixes model-routing fields: "
                + ", ".join(sorted(str(item) for item in overlap)),
            )
        )


def capability_status(document: object, provider_id: str, name: str) -> str:
    """Return supported, unsupported, or unknown. Missing entries stay unknown.

    Never infers from sibling rows, vendor aliases, or absent providers.
    """

    if not isinstance(document, Mapping):
        return "unknown"
    if not isinstance(provider_id, str) or not provider_id.strip():
        return "unknown"
    if not isinstance(name, str) or not name.strip():
        return "unknown"
    if name in VENDOR_ALIASES:
        return "unknown"
    providers = document.get("providers")
    if not isinstance(providers, list):
        return "unknown"
    for provider in providers:
        if not isinstance(provider, Mapping):
            continue
        if provider.get("provider_id") != provider_id:
            continue
        capabilities = provider.get("capabilities")
        if not isinstance(capabilities, list):
            return "unknown"
        for row in capabilities:
            if not isinstance(row, Mapping):
                continue
            if row.get("name") != name:
                continue
            status = row.get("status")
            if status in STATUS_SET:
                return str(status)
            return "unknown"
        return "unknown"
    return "unknown"


def validate_provider_capability_matrix(document: object) -> list[str]:
    """Return fail-closed violations for one provider-capability matrix."""

    errors: list[str] = []
    if not isinstance(document, Mapping):
        return [_error("unknown root_type", "provider capability matrix must be an object")]

    _reject_routing_fields(document, "document", errors)

    unknown = set(document) - DOCUMENT_FIELDS
    if unknown:
        errors.append(
            _error(
                "unknown field",
                "document has unknown fields: " + ", ".join(sorted(str(item) for item in unknown)),
            )
        )
    missing = DOCUMENT_FIELDS - set(document)
    if missing:
        errors.append(
            _error(
                "missing_value field",
                "document missing fields: " + ", ".join(sorted(missing)),
            )
        )

    version = document.get("schema_version")
    if not isinstance(version, int) or isinstance(version, bool) or version != SCHEMA_VERSION:
        errors.append(
            _error(
                "unknown schema_version",
                f"schema_version must be exactly {SCHEMA_VERSION}",
            )
        )

    providers = document.get("providers")
    if not isinstance(providers, list):
        errors.append(_error("unknown providers_type", "providers must be a list"))
        return errors
    if not providers:
        errors.append(_error("missing_value providers", "providers must be a non-empty list"))
        return errors

    seen_providers: set[str] = set()
    for index, provider in enumerate(providers):
        prefix = f"providers[{index}]"
        if not isinstance(provider, Mapping):
            errors.append(_error("unknown provider_type", f"{prefix} must be an object"))
            continue
        _reject_routing_fields(provider, prefix, errors)
        unknown_provider = set(provider) - PROVIDER_FIELDS
        if unknown_provider:
            errors.append(
                _error(
                    "unknown field",
                    f"{prefix} has unknown fields: "
                    + ", ".join(sorted(str(item) for item in unknown_provider)),
                )
            )
        provider_id = provider.get("provider_id")
        if not isinstance(provider_id, str) or not provider_id.strip():
            errors.append(
                _error("missing_value provider_id", f"{prefix} provider_id must be a non-empty string")
            )
        elif provider_id in seen_providers:
            errors.append(
                _error("unknown duplicate_provider", f"{prefix} duplicates provider_id {provider_id!r}")
            )
        else:
            seen_providers.add(provider_id)

        capabilities = provider.get("capabilities")
        if not isinstance(capabilities, list):
            errors.append(_error("unknown capabilities_type", f"{prefix} capabilities must be a list"))
            continue

        seen_names: set[str] = set()
        for cap_index, row in enumerate(capabilities):
            loc = f"{prefix}.capabilities[{cap_index}]"
            _validate_capability_row(row, loc, seen_names, errors)
    return errors


def _validate_capability_row(
    row: object,
    loc: str,
    seen_names: set[str],
    errors: list[str],
) -> None:
    if not isinstance(row, Mapping):
        errors.append(_error("unknown capability_type", f"{loc} must be an object"))
        return
    _reject_routing_fields(row, loc, errors)
    unknown_row = set(row) - CAPABILITY_FIELDS
    if unknown_row:
        errors.append(
            _error(
                "unknown field",
                f"{loc} has unknown fields: " + ", ".join(sorted(str(item) for item in unknown_row)),
            )
        )

    name = row.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append(_error("missing_value name", f"{loc} name must be a non-empty string"))
        name = None
    elif name in seen_names:
        errors.append(_error("unknown duplicate_capability", f"{loc} duplicates capability {name!r}"))
    else:
        seen_names.add(name)

    status = row.get("status")
    if isinstance(status, bool) or status in GUESSED_STATUSES:
        errors.append(
            _error(
                "unknown guessed_status",
                f"{loc} status {status!r} is a guess; use supported, unsupported, or unknown",
            )
        )
    elif status not in STATUS_SET:
        errors.append(
            _error(
                "unknown status",
                f"{loc} status {status!r} is not in the closed set",
            )
        )

    if name is not None and name not in KNOWN_CAPABILITY_SET:
        if status in {"supported", "unsupported"}:
            errors.append(
                _error(
                    "unknown guessed_capability",
                    f"{loc} capability {name!r} is not in the closed set and cannot be guessed as {status}",
                )
            )
        elif status == "unknown":
            pass
        else:
            errors.append(
                _error(
                    "unknown capability",
                    f"{loc} capability {name!r} is not in the closed set and remains unknown",
                )
            )

    refs = row.get("evidence_refs")
    if status == "unknown":
        if refs is None:
            errors.append(
                _error(
                    "missing_value evidence_refs",
                    f"{loc} evidence_refs must be a list (empty allowed only for unknown)",
                )
            )
        elif not isinstance(refs, list):
            errors.append(
                _error(
                    "unknown evidence_refs_type",
                    f"{loc} evidence_refs must be a list",
                )
            )
        else:
            for ref_index, ref in enumerate(refs):
                if not isinstance(ref, str) or not ref.strip():
                    errors.append(
                        _error(
                            "unknown evidence_ref",
                            f"{loc} evidence_refs[{ref_index}] must be a non-empty string",
                        )
                    )
        return

    if not isinstance(refs, list) or not refs:
        errors.append(
            _error(
                "missing_value evidence_refs",
                f"{loc} {status or 'declared'} capability requires a non-empty evidence_refs list",
            )
        )
        return
    for ref_index, ref in enumerate(refs):
        if not isinstance(ref, str) or not ref.strip():
            errors.append(
                _error(
                    "unknown evidence_ref",
                    f"{loc} evidence_refs[{ref_index}] must be a non-empty string",
                )
            )


def load_document(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(_error("unreadable missing_doc", f"{path} is missing")) from exc
    except OSError as exc:
        raise SystemExit(
            _error("unreadable io_error", f"cannot read {path}: {type(exc).__name__}")
        ) from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(
            _error(
                "unreadable json",
                f"invalid JSON in {path} at line {exc.lineno}, column {exc.colno}",
            )
        ) from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="provider-capability matrix JSON document")
    args = parser.parse_args(argv)
    errors = validate_provider_capability_matrix(load_document(args.path))
    if errors:
        print("Provider-capability matrix validation failed:", file=sys.stderr)
        for item in errors:
            print(f"  {item}", file=sys.stderr)
        return 1
    print(f"Provider-capability matrix schema v{SCHEMA_VERSION} accepted {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
