"""Authorized deterministic black-box probe runner."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .contracts import (
    AuthorizationScope,
    EvidenceBundle,
    Observation,
    ProbeCase,
    ReverseEngineeringError,
    canonical_json,
    stable_digest,
)

Target = Callable[[Any], Any]
FeatureExtractor = Callable[[Any], Iterable[str]]


def _shape(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, str):
        return "text"
    if isinstance(value, bytes):
        return "bytes"
    if isinstance(value, Mapping):
        keys = sorted(f"{type(key).__name__}:{key!s}" for key in value.keys())
        return "mapping:" + stable_digest(keys)[:16]
    if isinstance(value, Sequence):
        return f"sequence:{len(value)}"
    if isinstance(value, set):
        return f"set:{len(value)}"
    return type(value).__name__


def _normalize_mapping_key(value: Any) -> dict[str, Any]:
    if value is None or isinstance(value, (str, int, float, bool)):
        canonical_json(value)
        return {"type": type(value).__name__, "value": value}
    if isinstance(value, bytes):
        return {"type": "bytes", "digest": stable_digest(list(value))}
    raise ReverseEngineeringError(
        f"unsupported mapping key type for deterministic normalization: {type(value).__name__}"
    )


def _normalized_output(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"bytes_sha256": stable_digest(list(value))}
    if isinstance(value, Mapping):
        entries = [
            [_normalize_mapping_key(key), _normalized_output(item)]
            for key, item in value.items()
        ]
        entries.sort(key=lambda pair: canonical_json(pair[0]))
        return {"mapping_entries": entries}
    if isinstance(value, tuple):
        return {"tuple": [_normalized_output(item) for item in value]}
    if isinstance(value, list):
        return {"list": [_normalized_output(item) for item in value]}
    if isinstance(value, set):
        normalized = [_normalized_output(item) for item in value]
        return {"set": sorted(normalized, key=canonical_json)}
    if isinstance(value, (str, int, float, bool)) or value is None:
        canonical_json(value)
        return value
    raise ReverseEngineeringError(
        f"unsupported output type for deterministic normalization: {type(value).__name__}"
    )


@dataclass
class ProbeRunner:
    authorization: AuthorizationScope
    feature_extractors: tuple[FeatureExtractor, ...] = ()

    def run(
        self,
        *,
        target_id: str,
        target: Target,
        probes: Sequence[ProbeCase],
        repeats: int = 1,
    ) -> EvidenceBundle:
        if not self.authorization.authorizes(target_id):
            raise ReverseEngineeringError(f"target {target_id!r} is outside authorization scope")
        if repeats < 1 or repeats > 32:
            raise ReverseEngineeringError("repeats must be within [1, 32]")
        if not probes:
            raise ReverseEngineeringError("at least one probe is required")

        seen_ids: set[str] = set()
        for probe in probes:
            if probe.probe_id in seen_ids:
                raise ReverseEngineeringError(f"duplicate probe_id: {probe.probe_id!r}")
            seen_ids.add(probe.probe_id)

        observations: list[Observation] = []
        for probe in probes:
            for ordinal in range(repeats):
                try:
                    output = target(probe.payload)
                except Exception as exc:
                    observations.append(
                        Observation(
                            target_id=target_id,
                            probe_id=probe.probe_id,
                            kind=probe.kind,
                            input_digest=probe.payload_digest,
                            output_digest=stable_digest({"error_type": type(exc).__name__}),
                            output_shape="error",
                            success=False,
                            error_type=type(exc).__name__,
                            ordinal=ordinal,
                        )
                    )
                    continue

                flags: set[str] = set()
                for extractor in self.feature_extractors:
                    flags.update(str(item) for item in extractor(output))
                normalized = _normalized_output(output)
                observations.append(
                    Observation(
                        target_id=target_id,
                        probe_id=probe.probe_id,
                        kind=probe.kind,
                        input_digest=probe.payload_digest,
                        output_digest=stable_digest(normalized),
                        output_shape=_shape(output),
                        success=True,
                        feature_flags=tuple(sorted(flags)),
                        ordinal=ordinal,
                    )
                )
        return EvidenceBundle(target_id=target_id, observations=tuple(observations))
