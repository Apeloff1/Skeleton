"""Deterministic render-graph execution for Jeeves modern engine eras.

The modern runtime already owns the era pass lists. This module gives those
passes executable dependency semantics without pretending to be a GPU driver.
It validates resource lifetimes and produces deterministic evidence for every
pass and resource version.

No wall clock, threads, driver state, random values, or host GPU APIs are used.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable, Mapping

from .game_engine_lab import (
    EngineEra,
    GameEngineLabError,
)

RENDER_GRAPH_ERAS = (
    EngineEra.HD,
    EngineEra.OPEN_WORLD,
    EngineEra.MODERN,
    EngineEra.NEXT,
)

MAX_GRAPH_PASSES = 32
MAX_GRAPH_RESOURCES = 64
EXTERNAL_RESOURCES = frozenset(
    {
        "instances",
        "frame_constants",
        "streaming_state",
    }
)


def _canonical(
    value: object,
) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _digest(
    value: object,
) -> str:
    return hashlib.sha256(
        _canonical(value).encode(
            "utf-8"
        )
    ).hexdigest()


def _token(
    value: str,
    label: str,
) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 64
        or not all(
            char.isalnum()
            or char in "_.-"
            for char in value
        )
    ):
        raise GameEngineLabError(
            f"{label} must be a bounded token"
        )
    return value


@dataclass(frozen=True, slots=True)
class RenderGraphPass:
    name: str
    reads: tuple[str, ...]
    writes: tuple[str, ...]
    stage: str
    optional: bool = False

    def __post_init__(self) -> None:
        _token(
            self.name,
            "render pass name",
        )
        _token(
            self.stage,
            "render pass stage",
        )
        if not self.writes:
            raise GameEngineLabError(
                "render pass requires at least one write"
            )
        if len(
            self.reads
        ) != len(set(self.reads)):
            raise GameEngineLabError(
                "render pass reads must be unique"
            )
        if len(
            self.writes
        ) != len(set(self.writes)):
            raise GameEngineLabError(
                "render pass writes must be unique"
            )
        if set(
            self.reads
        ) & set(
            self.writes
        ):
            raise GameEngineLabError(
                "render pass cannot read and write the same logical resource"
            )
        for resource in (
            self.reads
            + self.writes
        ):
            _token(
                resource,
                "render resource",
            )


@dataclass(frozen=True, slots=True)
class RenderGraphSpec:
    era: EngineEra
    passes: tuple[
        RenderGraphPass,
        ...,
    ]
    final_resource: str

    def __post_init__(self) -> None:
        if (
            self.era
            not in RENDER_GRAPH_ERAS
        ):
            raise GameEngineLabError(
                "render graph unavailable for this era"
            )
        if (
            not 1
            <= len(self.passes)
            <= MAX_GRAPH_PASSES
        ):
            raise GameEngineLabError(
                "render graph pass count outside bounds"
            )
        names = tuple(
            item.name
            for item in self.passes
        )
        if len(names) != len(set(names)):
            raise GameEngineLabError(
                "render graph pass names must be unique"
            )
        _token(
            self.final_resource,
            "final render resource",
        )
        validate_render_graph(
            self
        )

    def document(
        self,
    ) -> dict[str, object]:
        return {
            "schema_version": 1,
            "engine_era":
                self.era.value,
            "external_resources":
                sorted(
                    EXTERNAL_RESOURCES
                ),
            "passes": [
                {
                    "name":
                        item.name,
                    "stage":
                        item.stage,
                    "reads":
                        list(
                            item.reads
                        ),
                    "writes":
                        list(
                            item.writes
                        ),
                    "optional":
                        item.optional,
                }
                for item
                in self.passes
            ],
            "final_resource":
                self.final_resource,
        }


def validate_render_graph(
    spec: RenderGraphSpec,
) -> None:
    available = set(
        EXTERNAL_RESOURCES
    )
    all_resources = set(
        available
    )
    final_written = False
    for item in spec.passes:
        missing = (
            set(item.reads)
            - available
        )
        if missing:
            raise GameEngineLabError(
                (
                    f"render pass {item.name} reads "
                    f"uninitialized resources: {sorted(missing)}"
                )
            )
        for resource in item.writes:
            available.add(
                resource
            )
            all_resources.add(
                resource
            )
            if (
                resource
                == spec.final_resource
            ):
                final_written = True
        if (
            len(all_resources)
            > MAX_GRAPH_RESOURCES
        ):
            raise GameEngineLabError(
                "render graph resource budget exceeded"
            )
    if not final_written:
        raise GameEngineLabError(
            "render graph never writes final resource"
        )


def _pass(
    name: str,
    reads: tuple[str, ...],
    writes: tuple[str, ...],
    stage: str,
    *,
    optional: bool = False,
) -> RenderGraphPass:
    return RenderGraphPass(
        name,
        reads,
        writes,
        stage,
        optional,
    )


RENDER_GRAPHS: Mapping[
    EngineEra,
    RenderGraphSpec,
] = {
    EngineEra.HD: RenderGraphSpec(
        EngineEra.HD,
        (
            _pass(
                "depth_prepass",
                (
                    "instances",
                    "frame_constants",
                ),
                (
                    "depth",
                ),
                "graphics",
            ),
            _pass(
                "gbuffer",
                (
                    "instances",
                    "depth",
                    "frame_constants",
                ),
                (
                    "gbuffer_albedo",
                    "gbuffer_normal",
                    "gbuffer_material",
                ),
                "graphics",
            ),
            _pass(
                "lighting",
                (
                    "depth",
                    "gbuffer_albedo",
                    "gbuffer_normal",
                    "gbuffer_material",
                    "frame_constants",
                ),
                (
                    "hdr_lit",
                ),
                "graphics",
            ),
            _pass(
                "transparent",
                (
                    "instances",
                    "depth",
                    "hdr_lit",
                    "frame_constants",
                ),
                (
                    "hdr_scene",
                ),
                "graphics",
            ),
            _pass(
                "post",
                (
                    "hdr_scene",
                    "frame_constants",
                ),
                (
                    "display",
                ),
                "graphics",
            ),
        ),
        "display",
    ),
    EngineEra.OPEN_WORLD: RenderGraphSpec(
        EngineEra.OPEN_WORLD,
        (
            _pass(
                "shadow",
                (
                    "instances",
                    "streaming_state",
                    "frame_constants",
                ),
                (
                    "shadow_atlas",
                ),
                "graphics",
            ),
            _pass(
                "depth_prepass",
                (
                    "instances",
                    "streaming_state",
                    "frame_constants",
                ),
                (
                    "depth",
                ),
                "graphics",
            ),
            _pass(
                "gbuffer",
                (
                    "instances",
                    "depth",
                    "streaming_state",
                    "frame_constants",
                ),
                (
                    "gbuffer_albedo",
                    "gbuffer_normal",
                    "gbuffer_material",
                ),
                "graphics",
            ),
            _pass(
                "lighting",
                (
                    "depth",
                    "shadow_atlas",
                    "gbuffer_albedo",
                    "gbuffer_normal",
                    "gbuffer_material",
                    "frame_constants",
                ),
                (
                    "hdr_lit",
                ),
                "graphics",
            ),
            _pass(
                "transparent",
                (
                    "instances",
                    "depth",
                    "hdr_lit",
                    "frame_constants",
                ),
                (
                    "hdr_scene",
                ),
                "graphics",
            ),
            _pass(
                "post",
                (
                    "hdr_scene",
                    "frame_constants",
                ),
                (
                    "display",
                ),
                "graphics",
            ),
        ),
        "display",
    ),
    EngineEra.MODERN: RenderGraphSpec(
        EngineEra.MODERN,
        (
            _pass(
                "cull",
                (
                    "instances",
                    "streaming_state",
                    "frame_constants",
                ),
                (
                    "visible_instances",
                ),
                "compute",
            ),
            _pass(
                "virtual_geometry",
                (
                    "visible_instances",
                    "frame_constants",
                ),
                (
                    "depth",
                    "visibility_buffer",
                ),
                "mesh",
            ),
            _pass(
                "gbuffer",
                (
                    "visible_instances",
                    "depth",
                    "visibility_buffer",
                    "frame_constants",
                ),
                (
                    "gbuffer_albedo",
                    "gbuffer_normal",
                    "gbuffer_material",
                ),
                "graphics",
            ),
            _pass(
                "ray_queries",
                (
                    "depth",
                    "gbuffer_normal",
                    "frame_constants",
                ),
                (
                    "ray_visibility",
                ),
                "compute",
            ),
            _pass(
                "lighting",
                (
                    "depth",
                    "gbuffer_albedo",
                    "gbuffer_normal",
                    "gbuffer_material",
                    "ray_visibility",
                    "frame_constants",
                ),
                (
                    "hdr_scene",
                ),
                "compute",
            ),
            _pass(
                "post",
                (
                    "hdr_scene",
                    "frame_constants",
                ),
                (
                    "display",
                ),
                "compute",
            ),
        ),
        "display",
    ),
    EngineEra.NEXT: RenderGraphSpec(
        EngineEra.NEXT,
        (
            _pass(
                "cull",
                (
                    "instances",
                    "streaming_state",
                    "frame_constants",
                ),
                (
                    "visible_instances",
                ),
                "compute",
            ),
            _pass(
                "virtual_geometry",
                (
                    "visible_instances",
                    "frame_constants",
                ),
                (
                    "depth",
                    "visibility_buffer",
                ),
                "mesh",
            ),
            _pass(
                "adaptive_material",
                (
                    "visible_instances",
                    "visibility_buffer",
                    "frame_constants",
                ),
                (
                    "material_attributes",
                ),
                "compute",
            ),
            _pass(
                "ray_queries",
                (
                    "depth",
                    "material_attributes",
                    "frame_constants",
                ),
                (
                    "ray_visibility",
                    "ray_radiance",
                ),
                "compute",
            ),
            _pass(
                "lighting",
                (
                    "depth",
                    "material_attributes",
                    "ray_visibility",
                    "ray_radiance",
                    "frame_constants",
                ),
                (
                    "hdr_scene",
                ),
                "compute",
            ),
            _pass(
                "post",
                (
                    "hdr_scene",
                    "frame_constants",
                ),
                (
                    "display",
                ),
                "compute",
            ),
        ),
        "display",
    ),
}


def render_graph_spec(
    era: EngineEra | str,
) -> RenderGraphSpec:
    try:
        key = (
            era
            if isinstance(era, EngineEra)
            else EngineEra(str(era))
        )
    except ValueError as exc:
        raise GameEngineLabError(
            f"unknown engine era: {era!r}"
        ) from exc
    try:
        return RENDER_GRAPHS[key]
    except KeyError as exc:
        raise GameEngineLabError(
            f"render graph unavailable for {key.value}"
        ) from exc


@dataclass(frozen=True, slots=True)
class PassEvidence:
    index: int
    name: str
    stage: str
    read_versions: tuple[
        tuple[str, str],
        ...,
    ]
    written_versions: tuple[
        tuple[str, str],
        ...,
    ]
    digest: str


@dataclass(frozen=True, slots=True)
class RenderGraphEvidence:
    era: EngineEra
    passes: tuple[
        PassEvidence,
        ...,
    ]
    resources: tuple[
        tuple[str, str],
        ...,
    ]
    final_resource: str
    final_digest: str
    graph_digest: str

    @property
    def pass_names(
        self,
    ) -> tuple[str, ...]:
        return tuple(
            item.name
            for item in self.passes
        )


def _external_digest(
    name: str,
    value: object,
) -> str:
    return _digest(
        {
            "resource": name,
            "value": value,
        }
    )


class RenderGraphExecutor:
    """Pure deterministic resource-version executor."""

    def __init__(
        self,
        spec: RenderGraphSpec,
    ) -> None:
        validate_render_graph(
            spec
        )
        self.spec = spec

    def execute(
        self,
        *,
        instances: object,
        frame_constants: object,
        streaming_state: object,
        disabled_passes: Iterable[
            str
        ] = (),
    ) -> RenderGraphEvidence:
        disabled = frozenset(
            disabled_passes
        )
        known_names = {
            item.name
            for item in self.spec.passes
        }
        unknown = (
            disabled
            - known_names
        )
        if unknown:
            raise GameEngineLabError(
                (
                    "cannot disable unknown render passes: "
                    f"{sorted(unknown)}"
                )
            )
        for item in self.spec.passes:
            if (
                item.name in disabled
                and not item.optional
            ):
                raise GameEngineLabError(
                    f"required render pass cannot be disabled: {item.name}"
                )

        resources = {
            "instances":
                _external_digest(
                    "instances",
                    instances,
                ),
            "frame_constants":
                _external_digest(
                    "frame_constants",
                    frame_constants,
                ),
            "streaming_state":
                _external_digest(
                    "streaming_state",
                    streaming_state,
                ),
        }
        evidence: list[
            PassEvidence
        ] = []
        for index, item in enumerate(
            self.spec.passes
        ):
            if item.name in disabled:
                continue
            missing = [
                resource
                for resource in item.reads
                if resource
                not in resources
            ]
            if missing:
                raise GameEngineLabError(
                    (
                        f"render pass {item.name} has "
                        f"missing runtime resources: {missing}"
                    )
                )
            reads = tuple(
                (
                    resource,
                    resources[
                        resource
                    ],
                )
                for resource
                in item.reads
            )
            pass_identity = {
                "engine_era":
                    self.spec.era.value,
                "index": index,
                "name": item.name,
                "stage": item.stage,
                "reads": reads,
                "writes":
                    item.writes,
            }
            pass_digest = _digest(
                pass_identity
            )
            writes = []
            for ordinal, resource in enumerate(
                item.writes
            ):
                version = _digest(
                    {
                        "pass":
                            pass_digest,
                        "resource":
                            resource,
                        "ordinal":
                            ordinal,
                    }
                )
                resources[
                    resource
                ] = version
                writes.append(
                    (
                        resource,
                        version,
                    )
                )
            evidence.append(
                PassEvidence(
                    index,
                    item.name,
                    item.stage,
                    reads,
                    tuple(writes),
                    pass_digest,
                )
            )

        try:
            final_digest = resources[
                self.spec.final_resource
            ]
        except KeyError as exc:
            raise GameEngineLabError(
                "render graph execution produced no final resource"
            ) from exc
        graph_identity = {
            "engine_era":
                self.spec.era.value,
            "passes": [
                item.digest
                for item
                in evidence
            ],
            "resources":
                sorted(
                    resources.items()
                ),
            "final_resource":
                self.spec.final_resource,
            "final_digest":
                final_digest,
        }
        return RenderGraphEvidence(
            self.spec.era,
            tuple(evidence),
            tuple(
                sorted(
                    resources.items()
                )
            ),
            self.spec.final_resource,
            final_digest,
            _digest(
                graph_identity
            ),
        )


def execute_render_graph(
    era: EngineEra | str,
    *,
    instances: object,
    frame_constants: object,
    streaming_state: object,
) -> RenderGraphEvidence:
    spec = render_graph_spec(
        era
    )
    return RenderGraphExecutor(
        spec
    ).execute(
        instances=instances,
        frame_constants=
            frame_constants,
        streaming_state=
            streaming_state,
    )
