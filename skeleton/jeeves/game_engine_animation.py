"""Deterministic historical animation runtime for Jeeves game sandboxes.

The repository already has a text-to-animation API that generates rig and
animation descriptions. This module is different: it is the bounded runtime
authority that evaluates animation inside era sandboxes.

Capabilities progress historically:
- Pong/arcade: discrete sprite-frame stepping.
- 8/16-bit: richer frame tracks and simple transform channels.
- early 3D: object transform tracks.
- fixed-function 3D: skeletal channels.
- shader/HD: multi-clip blending and smooth interpolation.
- open-world/modern: root motion and larger skeletal budgets.
- modern/next: bounded two-bone IK control and larger deterministic pose sets.

Compiled animation is data-only under animation/compiled/. No generated source,
host clock, random number source, or external animation service participates in
authoritative playback.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping

from .game_engine_lab import (
    EngineEra,
    GameEngineLabError,
    SandboxPatch,
)
from .game_engine_runtime import RoutedEngineSandbox


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _digest(value: object) -> str:
    return hashlib.sha256(
        _canonical(value).encode("utf-8")
    ).hexdigest()


def _finite(
    value: float,
    label: str,
) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise GameEngineLabError(
            f"{label} must be finite"
        )
    return result


class Interpolation(str, Enum):
    STEP = "step"
    LINEAR = "linear"
    SMOOTH = "smooth"


class TrackKind(str, Enum):
    SPRITE_INDEX = "sprite_index"
    TRANSLATION_X = "translation_x"
    TRANSLATION_Y = "translation_y"
    TRANSLATION_Z = "translation_z"
    ROTATION_DEG = "rotation_deg"
    SCALE = "scale"
    BONE_ROTATION_DEG = "bone_rotation_deg"
    ROOT_X = "root_x"
    ROOT_Z = "root_z"
    IK_WEIGHT = "ik_weight"


@dataclass(frozen=True, slots=True)
class AnimationEraPolicy:
    era: EngineEra
    max_clips: int
    max_tracks_per_clip: int
    max_keyframes_per_track: int
    max_bones: int
    allowed_tracks: tuple[TrackKind, ...]
    interpolation: tuple[Interpolation, ...]
    blending: bool
    root_motion: bool
    ik: bool
    max_layers: int
    pose_precision: int

    def __post_init__(self) -> None:
        for value in (
            self.max_clips,
            self.max_tracks_per_clip,
            self.max_keyframes_per_track,
            self.max_layers,
        ):
            if value < 1:
                raise GameEngineLabError(
                    "animation policy positive bounds required"
                )
        if (
            type(self.pose_precision) is not int
            or not 0 <= self.pose_precision <= 15
        ):
            raise GameEngineLabError(
                "animation pose precision outside [0, 15]"
            )
        if self.max_bones < 0:
            raise GameEngineLabError(
                "animation bone budget cannot be negative"
            )
        if not self.allowed_tracks:
            raise GameEngineLabError(
                "animation policy requires tracks"
            )
        if not self.interpolation:
            raise GameEngineLabError(
                "animation policy requires interpolation modes"
            )


SPRITE_TRACKS = (
    TrackKind.SPRITE_INDEX,
)
TWO_D_TRACKS = SPRITE_TRACKS + (
    TrackKind.TRANSLATION_X,
    TrackKind.TRANSLATION_Y,
    TrackKind.ROTATION_DEG,
    TrackKind.SCALE,
)
OBJECT_3D_TRACKS = TWO_D_TRACKS + (
    TrackKind.TRANSLATION_Z,
)
SKELETAL_TRACKS = OBJECT_3D_TRACKS + (
    TrackKind.BONE_ROTATION_DEG,
)
ROOT_TRACKS = SKELETAL_TRACKS + (
    TrackKind.ROOT_X,
    TrackKind.ROOT_Z,
)
IK_TRACKS = ROOT_TRACKS + (
    TrackKind.IK_WEIGHT,
)


def _policy(
    era: EngineEra,
    clips: int,
    tracks: int,
    keys: int,
    bones: int,
    allowed: tuple[TrackKind, ...],
    interpolation: tuple[Interpolation, ...],
    *,
    blending: bool,
    root_motion: bool,
    ik: bool,
    layers: int,
    precision: int,
) -> AnimationEraPolicy:
    return AnimationEraPolicy(
        era,
        clips,
        tracks,
        keys,
        bones,
        allowed,
        interpolation,
        blending,
        root_motion,
        ik,
        layers,
        precision,
    )


ANIMATION_POLICIES: Mapping[
    EngineEra,
    AnimationEraPolicy,
] = {
    EngineEra.PONG: _policy(
        EngineEra.PONG,
        2,
        2,
        8,
        0,
        SPRITE_TRACKS,
        (Interpolation.STEP,),
        blending=False,
        root_motion=False,
        ik=False,
        layers=1,
        precision=0,
    ),
    EngineEra.ARCADE: _policy(
        EngineEra.ARCADE,
        8,
        4,
        16,
        0,
        SPRITE_TRACKS,
        (Interpolation.STEP,),
        blending=False,
        root_motion=False,
        ik=False,
        layers=1,
        precision=0,
    ),
    EngineEra.EIGHT_BIT: _policy(
        EngineEra.EIGHT_BIT,
        16,
        8,
        32,
        0,
        TWO_D_TRACKS,
        (
            Interpolation.STEP,
            Interpolation.LINEAR,
        ),
        blending=False,
        root_motion=False,
        ik=False,
        layers=1,
        precision=4,
    ),
    EngineEra.SIXTEEN_BIT: _policy(
        EngineEra.SIXTEEN_BIT,
        32,
        16,
        64,
        0,
        TWO_D_TRACKS,
        (
            Interpolation.STEP,
            Interpolation.LINEAR,
        ),
        blending=True,
        root_motion=False,
        ik=False,
        layers=2,
        precision=5,
    ),
    EngineEra.EARLY_3D: _policy(
        EngineEra.EARLY_3D,
        48,
        24,
        96,
        0,
        OBJECT_3D_TRACKS,
        (
            Interpolation.STEP,
            Interpolation.LINEAR,
        ),
        blending=True,
        root_motion=False,
        ik=False,
        layers=2,
        precision=5,
    ),
    EngineEra.FIXED_3D: _policy(
        EngineEra.FIXED_3D,
        64,
        64,
        128,
        32,
        SKELETAL_TRACKS,
        (
            Interpolation.STEP,
            Interpolation.LINEAR,
        ),
        blending=True,
        root_motion=False,
        ik=False,
        layers=3,
        precision=6,
    ),
    EngineEra.SHADER: _policy(
        EngineEra.SHADER,
        96,
        128,
        192,
        64,
        SKELETAL_TRACKS,
        tuple(Interpolation),
        blending=True,
        root_motion=False,
        ik=False,
        layers=4,
        precision=6,
    ),
    EngineEra.HD: _policy(
        EngineEra.HD,
        128,
        192,
        256,
        128,
        ROOT_TRACKS,
        tuple(Interpolation),
        blending=True,
        root_motion=True,
        ik=False,
        layers=6,
        precision=7,
    ),
    EngineEra.OPEN_WORLD: _policy(
        EngineEra.OPEN_WORLD,
        192,
        256,
        384,
        160,
        ROOT_TRACKS,
        tuple(Interpolation),
        blending=True,
        root_motion=True,
        ik=False,
        layers=8,
        precision=7,
    ),
    EngineEra.MODERN: _policy(
        EngineEra.MODERN,
        256,
        384,
        512,
        256,
        IK_TRACKS,
        tuple(Interpolation),
        blending=True,
        root_motion=True,
        ik=True,
        layers=12,
        precision=8,
    ),
    EngineEra.NEXT: _policy(
        EngineEra.NEXT,
        512,
        512,
        768,
        512,
        IK_TRACKS,
        tuple(Interpolation),
        blending=True,
        root_motion=True,
        ik=True,
        layers=16,
        precision=9,
    ),
}


def animation_policy(
    era: EngineEra | str,
) -> AnimationEraPolicy:
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
    return ANIMATION_POLICIES[key]


@dataclass(frozen=True, slots=True)
class AnimationKeyframe:
    tick: int
    value: float

    def __post_init__(self) -> None:
        if (
            type(self.tick) is not int
            or self.tick < 0
            or self.tick > 1_000_000
        ):
            raise GameEngineLabError(
                "animation keyframe tick outside range"
            )
        _finite(
            self.value,
            "animation keyframe value",
        )


@dataclass(frozen=True, slots=True)
class AnimationTrack:
    target: str
    kind: TrackKind
    interpolation: Interpolation
    keyframes: tuple[
        AnimationKeyframe,
        ...,
    ]

    def __post_init__(self) -> None:
        if (
            not self.target
            or len(self.target) > 64
            or not all(
                char.isalnum()
                or char in "_.-"
                for char in self.target
            )
        ):
            raise GameEngineLabError(
                "animation target must be bounded and path-safe"
            )
        if not isinstance(
            self.kind,
            TrackKind,
        ):
            object.__setattr__(
                self,
                "kind",
                TrackKind(
                    str(self.kind)
                ),
            )
        if not isinstance(
            self.interpolation,
            Interpolation,
        ):
            object.__setattr__(
                self,
                "interpolation",
                Interpolation(
                    str(self.interpolation)
                ),
            )
        if not self.keyframes:
            raise GameEngineLabError(
                "animation track requires keyframes"
            )
        ticks = tuple(
            key.tick
            for key
            in self.keyframes
        )
        if ticks != tuple(
            sorted(ticks)
        ):
            raise GameEngineLabError(
                "animation keyframes must be tick-sorted"
            )
        if len(ticks) != len(
            set(ticks)
        ):
            raise GameEngineLabError(
                "animation keyframe ticks must be unique"
            )


@dataclass(frozen=True, slots=True)
class AnimationClipSource:
    clip_id: str
    duration_ticks: int
    looping: bool
    tracks: tuple[
        AnimationTrack,
        ...,
    ]

    def __post_init__(self) -> None:
        if (
            not self.clip_id
            or len(self.clip_id) > 64
            or not all(
                char.isalnum()
                or char in "_.-"
                for char in self.clip_id
            )
        ):
            raise GameEngineLabError(
                "animation clip id must be bounded and path-safe"
            )
        if (
            type(self.duration_ticks)
            is not int
            or not 1
            <= self.duration_ticks
            <= 1_000_000
        ):
            raise GameEngineLabError(
                "animation duration outside range"
            )
        if not self.tracks:
            raise GameEngineLabError(
                "animation clip requires tracks"
            )
        for track in self.tracks:
            if (
                track.keyframes[-1].tick
                > self.duration_ticks
            ):
                raise GameEngineLabError(
                    "animation keyframe exceeds clip duration"
                )


@dataclass(frozen=True, slots=True)
class AnimationSceneSource:
    clips: tuple[
        AnimationClipSource,
        ...,
    ]

    def __post_init__(self) -> None:
        if not self.clips:
            raise GameEngineLabError(
                "animation scene requires clips"
            )


def _track_identity(
    track: AnimationTrack,
) -> tuple[str, str]:
    return (
        track.target,
        track.kind.value,
    )


def validate_animation_source(
    era: EngineEra | str,
    source: AnimationSceneSource,
) -> None:
    policy = animation_policy(
        era
    )
    if (
        len(source.clips)
        > policy.max_clips
    ):
        raise GameEngineLabError(
            "animation clip budget exceeded"
        )
    clip_ids = tuple(
        clip.clip_id
        for clip in source.clips
    )
    if len(clip_ids) != len(
        set(clip_ids)
    ):
        raise GameEngineLabError(
            "animation clip ids must be unique"
        )
    for clip in source.clips:
        if (
            len(clip.tracks)
            > policy.max_tracks_per_clip
        ):
            raise GameEngineLabError(
                "animation track budget exceeded"
            )
        identities = tuple(
            _track_identity(
                track
            )
            for track
            in clip.tracks
        )
        if len(identities) != len(
            set(identities)
        ):
            raise GameEngineLabError(
                "animation track identities must be unique within a clip"
            )
        bone_targets = {
            track.target
            for track in clip.tracks
            if (
                track.kind
                in policy.allowed_tracks
                and (
                    track.kind
                    is TrackKind.BONE_ROTATION_DEG
                    or track.kind
                    is TrackKind.IK_WEIGHT
                )
            )
        }
        if (
            len(bone_targets)
            > policy.max_bones
        ):
            raise GameEngineLabError(
                "animation bone budget exceeded"
            )
        for track in clip.tracks:
            if (
                track.kind
                not in policy.allowed_tracks
            ):
                raise GameEngineLabError(
                    f"{track.kind.value} unavailable in {policy.era.value}"
                )
            if (
                track.interpolation
                not in policy.interpolation
            ):
                raise GameEngineLabError(
                    f"{track.interpolation.value} interpolation unavailable"
                )
            if (
                len(track.keyframes)
                > policy.max_keyframes_per_track
            ):
                raise GameEngineLabError(
                    "animation keyframe budget exceeded"
                )
            if (
                track.kind
                in {
                    TrackKind.ROOT_X,
                    TrackKind.ROOT_Z,
                }
                and not policy.root_motion
            ):
                raise GameEngineLabError(
                    "root motion unavailable in this engine era"
                )
            if (
                track.kind
                is TrackKind.IK_WEIGHT
                and not policy.ik
            ):
                raise GameEngineLabError(
                    "IK control unavailable in this engine era"
                )
            if (
                track.kind
                is TrackKind.SPRITE_INDEX
            ):
                for key in track.keyframes:
                    if (
                        key.value < 0
                        or key.value
                        != math.floor(
                            key.value
                        )
                    ):
                        raise GameEngineLabError(
                            "sprite frame values must be nonnegative integers"
                        )
            if (
                track.kind
                is TrackKind.IK_WEIGHT
            ):
                for key in track.keyframes:
                    if not 0 <= key.value <= 1:
                        raise GameEngineLabError(
                            "IK weight must be within [0, 1]"
                        )


def _keyframe_document(
    keyframe: AnimationKeyframe,
) -> dict[str, object]:
    return {
        "tick": keyframe.tick,
        "value": keyframe.value,
    }


def _track_document(
    track: AnimationTrack,
) -> dict[str, object]:
    return {
        "target": track.target,
        "kind": track.kind.value,
        "interpolation":
            track.interpolation.value,
        "keyframes": [
            _keyframe_document(
                keyframe
            )
            for keyframe
            in track.keyframes
        ],
    }


def _clip_document(
    clip: AnimationClipSource,
) -> dict[str, object]:
    return {
        "clip_id": clip.clip_id,
        "duration_ticks":
            clip.duration_ticks,
        "looping": clip.looping,
        "tracks": [
            _track_document(
                track
            )
            for track
            in clip.tracks
        ],
    }


def _policy_document(
    policy: AnimationEraPolicy,
) -> dict[str, object]:
    return {
        "engine_era":
            policy.era.value,
        "max_clips":
            policy.max_clips,
        "max_tracks_per_clip":
            policy.max_tracks_per_clip,
        "max_keyframes_per_track":
            policy.max_keyframes_per_track,
        "max_bones":
            policy.max_bones,
        "allowed_tracks": [
            kind.value
            for kind
            in policy.allowed_tracks
        ],
        "interpolation": [
            interpolation.value
            for interpolation
            in policy.interpolation
        ],
        "blending":
            policy.blending,
        "root_motion":
            policy.root_motion,
        "ik":
            policy.ik,
        "max_layers":
            policy.max_layers,
        "pose_precision":
            policy.pose_precision,
    }


@dataclass(frozen=True, slots=True)
class CompiledAnimationClip:
    clip_id: str
    duration_ticks: int
    looping: bool
    tracks: tuple[
        AnimationTrack,
        ...,
    ]
    digest: str

    def document(
        self,
    ) -> dict[str, object]:
        return {
            "schema_version": 1,
            "clip_id":
                self.clip_id,
            "duration_ticks":
                self.duration_ticks,
            "looping":
                self.looping,
            "tracks": [
                _track_document(
                    track
                )
                for track
                in self.tracks
            ],
            "digest":
                self.digest,
            "host_code_execution":
                False,
        }


@dataclass(frozen=True, slots=True)
class AnimationBuild:
    era: EngineEra
    clips: tuple[
        CompiledAnimationClip,
        ...,
    ]
    policy_digest: str
    source_digest: str
    manifest_digest: str

    def manifest(
        self,
    ) -> dict[str, object]:
        return {
            "schema_version": 1,
            "engine_era":
                self.era.value,
            "clip_count":
                len(self.clips),
            "clips": [
                {
                    "clip_id":
                        clip.clip_id,
                    "digest":
                        clip.digest,
                }
                for clip
                in self.clips
            ],
            "policy_digest":
                self.policy_digest,
            "source_digest":
                self.source_digest,
            "manifest_digest":
                self.manifest_digest,
            "host_code_execution":
                False,
        }


def compile_animation_build(
    era: EngineEra | str,
    source: AnimationSceneSource,
) -> AnimationBuild:
    policy = animation_policy(
        era
    )
    validate_animation_source(
        policy.era,
        source,
    )
    compiled: list[
        CompiledAnimationClip
    ] = []
    for clip in sorted(
        source.clips,
        key=lambda value:
            value.clip_id,
    ):
        identity = (
            _clip_document(
                clip
            )
        )
        compiled.append(
            CompiledAnimationClip(
                clip.clip_id,
                clip.duration_ticks,
                clip.looping,
                clip.tracks,
                _digest(
                    identity
                ),
            )
        )
    source_doc = {
        "clips": [
            _clip_document(
                clip
            )
            for clip
            in sorted(
                source.clips,
                key=lambda value:
                    value.clip_id,
            )
        ],
    }
    policy_digest = _digest(
        _policy_document(
            policy
        )
    )
    source_digest = _digest(
        source_doc
    )
    identity = {
        "schema_version": 1,
        "engine_era":
            policy.era.value,
        "policy_digest":
            policy_digest,
        "source_digest":
            source_digest,
        "clips": [
            {
                "clip_id":
                    clip.clip_id,
                "digest":
                    clip.digest,
            }
            for clip
            in compiled
        ],
    }
    return AnimationBuild(
        policy.era,
        tuple(compiled),
        policy_digest,
        source_digest,
        _digest(identity),
    )


def animation_build_patches(
    build: AnimationBuild,
) -> tuple[SandboxPatch, ...]:
    patches = [
        SandboxPatch(
            "animation/compiled/manifest.json",
            json.dumps(
                build.manifest(),
                indent=2,
                sort_keys=True,
            )
            + "\n",
        ),
        SandboxPatch(
            "animation/compiled/policy.json",
            json.dumps(
                _policy_document(
                    animation_policy(
                        build.era
                    )
                ),
                indent=2,
                sort_keys=True,
            )
            + "\n",
        ),
    ]
    for clip in build.clips:
        patches.append(
            SandboxPatch(
                (
                    "animation/compiled/"
                    + clip.clip_id
                    + ".clip.json"
                ),
                json.dumps(
                    clip.document(),
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
            )
        )
    return tuple(patches)


def attach_animation_build(
    sandbox: RoutedEngineSandbox,
    source: AnimationSceneSource,
) -> RoutedEngineSandbox:
    build = compile_animation_build(
        sandbox.era,
        source,
    )
    return sandbox.apply(
        tuple(
            SandboxPatch(
                patch.path,
                patch.content,
                sandbox.tree.file_digest(
                    patch.path
                ),
            )
            for patch
            in animation_build_patches(
                build
            )
        )
    )


def canonical_animation_patches(
    sandbox: RoutedEngineSandbox,
    source: AnimationSceneSource,
) -> tuple[SandboxPatch, ...]:
    build = compile_animation_build(
        sandbox.era,
        source,
    )
    expected = {
        patch.path: patch.content
        for patch
        in animation_build_patches(
            build
        )
    }
    existing = {
        path
        for path
        in sandbox.tree.files
        if path.startswith(
            "animation/compiled/"
        )
    }
    patches: list[
        SandboxPatch
    ] = []
    for path in sorted(
        set(expected)
        | existing
    ):
        wanted = expected.get(
            path
        )
        try:
            current = sandbox.tree.read(
                path
            )
        except GameEngineLabError:
            current = None
        if current == wanted:
            continue
        patches.append(
            SandboxPatch(
                path,
                wanted,
                sandbox.tree.file_digest(
                    path
                ),
            )
        )
    return tuple(patches)


@dataclass(frozen=True, slots=True)
class PoseValue:
    target: str
    kind: TrackKind
    value: float


@dataclass(frozen=True, slots=True)
class AnimationPose:
    clip_id: str
    tick: int
    values: tuple[
        PoseValue,
        ...,
    ]
    digest: str


@dataclass(frozen=True, slots=True)
class AnimatorSnapshot:
    era: EngineEra
    clip_id: str
    local_tick: float
    absolute_tick: int
    playback_rate: float
    digest: str


def _sample_track(
    track: AnimationTrack,
    tick: float,
    precision: int,
) -> float:
    keys = track.keyframes
    if tick <= keys[0].tick:
        return round(
            keys[0].value,
            precision,
        )
    if tick >= keys[-1].tick:
        return round(
            keys[-1].value,
            precision,
        )

    left = keys[0]
    right = keys[-1]
    for index in range(
        1,
        len(keys),
    ):
        if tick < keys[index].tick:
            left = keys[
                index - 1
            ]
            right = keys[index]
            break

    if (
        track.interpolation
        is Interpolation.STEP
    ):
        value = left.value
    else:
        span = (
            right.tick
            - left.tick
        )
        alpha = (
            0.0
            if span <= 0
            else (
                tick
                - left.tick
            )
            / span
        )
        if (
            track.interpolation
            is Interpolation.SMOOTH
        ):
            alpha = (
                alpha
                * alpha
                * (
                    3.0
                    - 2.0
                    * alpha
                )
            )
        value = (
            left.value
            + (
                right.value
                - left.value
            )
            * alpha
        )
    if (
        track.kind
        is TrackKind.SPRITE_INDEX
    ):
        value = float(
            math.floor(
                value
                + 1e-12
            )
        )
    return round(
        value,
        precision,
    )


class HistoricalAnimator:
    """Fixed-tick deterministic clip player and blender."""

    def __init__(
        self,
        era: EngineEra | str,
        source: AnimationSceneSource,
    ) -> None:
        self.policy = animation_policy(
            era
        )
        validate_animation_source(
            self.policy.era,
            source,
        )
        self._clips = {
            clip.clip_id: clip
            for clip in source.clips
        }
        self.clip_id = (
            source.clips[0].clip_id
        )
        self.local_tick = 0.0
        self.absolute_tick = 0
        self.playback_rate = 1.0

    @property
    def current_clip(
        self,
    ) -> AnimationClipSource:
        return self._clips[
            self.clip_id
        ]

    def play(
        self,
        clip_id: str,
        *,
        restart: bool = True,
        playback_rate: float = 1.0,
    ) -> None:
        if clip_id not in self._clips:
            raise GameEngineLabError(
                "unknown animation clip"
            )
        rate = _finite(
            playback_rate,
            "animation playback rate",
        )
        if not 0 < rate <= 8:
            raise GameEngineLabError(
                "animation playback rate outside (0, 8]"
            )
        if (
            restart
            or clip_id
            != self.clip_id
        ):
            self.local_tick = 0.0
        self.clip_id = clip_id
        self.playback_rate = rate

    def _normalized_tick(
        self,
        clip: AnimationClipSource,
        tick: float,
    ) -> float:
        if clip.looping:
            return tick % (
                clip.duration_ticks
                + 1
            )
        return min(
            float(
                clip.duration_ticks
            ),
            max(
                0.0,
                tick,
            ),
        )

    def sample(
        self,
        clip_id: str | None = None,
        *,
        tick: float | None = None,
    ) -> AnimationPose:
        active_id = (
            clip_id
            if clip_id is not None
            else self.clip_id
        )
        if active_id not in self._clips:
            raise GameEngineLabError(
                "unknown animation clip"
            )
        clip = self._clips[
            active_id
        ]
        sample_tick = (
            float(self.local_tick)
            if tick is None
            else _finite(
                tick,
                "animation sample tick",
            )
        )
        sample_tick = (
            self._normalized_tick(
                clip,
                sample_tick,
            )
        )
        values = tuple(
            PoseValue(
                track.target,
                track.kind,
                _sample_track(
                    track,
                    sample_tick,
                    self.policy.pose_precision,
                ),
            )
            for track
            in sorted(
                clip.tracks,
                key=lambda value: (
                    value.target,
                    value.kind.value,
                ),
            )
        )
        payload = {
            "clip_id": active_id,
            "tick": round(
                sample_tick,
                self.policy.pose_precision,
            ),
            "values": [
                (
                    value.target,
                    value.kind.value,
                    value.value,
                )
                for value
                in values
            ],
        }
        return AnimationPose(
            active_id,
            int(
                math.floor(
                    sample_tick
                )
            ),
            values,
            _digest(payload),
        )

    def step(
        self,
        count: int = 1,
    ) -> tuple[
        AnimationPose,
        ...,
    ]:
        if (
            type(count) is not int
            or not 1
            <= count
            <= 100_000
        ):
            raise GameEngineLabError(
                "animation step count outside [1, 100000]"
            )
        poses: list[
            AnimationPose
        ] = []
        for _ in range(count):
            poses.append(
                self.sample()
            )
            next_tick = (
                self.local_tick
                + self.playback_rate
            )
            clip = (
                self.current_clip
            )
            if clip.looping:
                next_tick %= (
                    clip.duration_ticks
                    + 1
                )
            else:
                next_tick = min(
                    float(
                        clip.duration_ticks
                    ),
                    next_tick,
                )
            self.local_tick = (
                next_tick
            )
            self.absolute_tick += 1
        return tuple(poses)

    def blend(
        self,
        left_clip: str,
        right_clip: str,
        alpha: float,
        *,
        tick: float | None = None,
    ) -> AnimationPose:
        if not self.policy.blending:
            raise GameEngineLabError(
                "animation blending unavailable in this engine era"
            )
        alpha = _finite(
            alpha,
            "animation blend alpha",
        )
        if not 0 <= alpha <= 1:
            raise GameEngineLabError(
                "animation blend alpha outside [0, 1]"
            )
        left = self.sample(
            left_clip,
            tick=tick,
        )
        right = self.sample(
            right_clip,
            tick=tick,
        )
        left_values = {
            (
                value.target,
                value.kind,
            ):
                value.value
            for value
            in left.values
        }
        right_values = {
            (
                value.target,
                value.kind,
            ):
                value.value
            for value
            in right.values
        }
        keys = sorted(
            set(left_values)
            | set(right_values),
            key=lambda value: (
                value[0],
                value[1].value,
            ),
        )
        values = tuple(
            PoseValue(
                target,
                kind,
                round(
                    left_values.get(
                        (
                            target,
                            kind,
                        ),
                        0.0,
                    )
                    * (
                        1.0
                        - alpha
                    )
                    + right_values.get(
                        (
                            target,
                            kind,
                        ),
                        0.0,
                    )
                    * alpha,
                    self.policy.pose_precision,
                ),
            )
            for target, kind in keys
        )
        payload = {
            "clip_id":
                f"{left_clip}+{right_clip}",
            "tick": (
                self.local_tick
                if tick is None
                else tick
            ),
            "alpha": alpha,
            "values": [
                (
                    value.target,
                    value.kind.value,
                    value.value,
                )
                for value
                in values
            ],
        }
        return AnimationPose(
            f"{left_clip}+{right_clip}",
            int(
                self.local_tick
                if tick is None
                else math.floor(
                    float(tick)
                )
            ),
            values,
            _digest(payload),
        )

    def root_motion_delta(
        self,
        clip_id: str,
        start_tick: float,
        end_tick: float,
    ) -> tuple[float, float]:
        if not self.policy.root_motion:
            raise GameEngineLabError(
                "root motion unavailable in this engine era"
            )
        start = self.sample(
            clip_id,
            tick=start_tick,
        )
        end = self.sample(
            clip_id,
            tick=end_tick,
        )

        def root(
            pose: AnimationPose,
            kind: TrackKind,
        ) -> float:
            for value in pose.values:
                if (
                    value.kind
                    is kind
                ):
                    return value.value
            return 0.0

        return (
            round(
                root(
                    end,
                    TrackKind.ROOT_X,
                )
                - root(
                    start,
                    TrackKind.ROOT_X,
                ),
                self.policy.pose_precision,
            ),
            round(
                root(
                    end,
                    TrackKind.ROOT_Z,
                )
                - root(
                    start,
                    TrackKind.ROOT_Z,
                ),
                self.policy.pose_precision,
            ),
        )

    def snapshot(
        self,
    ) -> AnimatorSnapshot:
        local_tick = float(
            self.local_tick
        )
        payload = {
            "era": self.policy.era.value,
            "clip_id": self.clip_id,
            "local_tick":
                local_tick,
            "absolute_tick":
                self.absolute_tick,
            "playback_rate":
                self.playback_rate,
        }
        return AnimatorSnapshot(
            self.policy.era,
            self.clip_id,
            local_tick,
            self.absolute_tick,
            self.playback_rate,
            _digest(payload),
        )

    def restore(
        self,
        snapshot: AnimatorSnapshot,
    ) -> None:
        if (
            snapshot.era
            is not self.policy.era
        ):
            raise GameEngineLabError(
                "animation snapshot era mismatch"
            )
        if snapshot.clip_id not in self._clips:
            raise GameEngineLabError(
                "animation snapshot references missing clip"
            )
        payload = {
            "era": snapshot.era.value,
            "clip_id":
                snapshot.clip_id,
            "local_tick":
                snapshot.local_tick,
            "absolute_tick":
                snapshot.absolute_tick,
            "playback_rate":
                snapshot.playback_rate,
        }
        if (
            _digest(payload)
            != snapshot.digest
        ):
            raise GameEngineLabError(
                "animation snapshot digest mismatch"
            )
        self.clip_id = (
            snapshot.clip_id
        )
        self.local_tick = (
            snapshot.local_tick
        )
        self.absolute_tick = (
            snapshot.absolute_tick
        )
        self.playback_rate = (
            snapshot.playback_rate
        )

    def fingerprint(
        self,
    ) -> str:
        return self.snapshot().digest


@dataclass(frozen=True, slots=True)
class IKResult:
    joint_x: float
    joint_y: float
    end_x: float
    end_y: float
    reached: bool
    digest: str


def solve_two_bone_ik(
    era: EngineEra | str,
    *,
    root_x: float,
    root_y: float,
    target_x: float,
    target_y: float,
    upper_length: float,
    lower_length: float,
    bend_sign: int = 1,
) -> IKResult:
    policy = animation_policy(
        era
    )
    if not policy.ik:
        raise GameEngineLabError(
            "two-bone IK unavailable in this engine era"
        )
    values = [
        _finite(
            value,
            "IK coordinate",
        )
        for value in (
            root_x,
            root_y,
            target_x,
            target_y,
            upper_length,
            lower_length,
        )
    ]
    (
        root_x,
        root_y,
        target_x,
        target_y,
        upper_length,
        lower_length,
    ) = values
    if (
        upper_length <= 0
        or lower_length <= 0
    ):
        raise GameEngineLabError(
            "IK bone lengths must be positive"
        )
    if bend_sign not in {
        -1,
        1,
    }:
        raise GameEngineLabError(
            "IK bend sign must be -1 or 1"
        )

    dx = (
        target_x
        - root_x
    )
    dy = (
        target_y
        - root_y
    )
    distance = math.hypot(
        dx,
        dy,
    )
    max_reach = (
        upper_length
        + lower_length
    )
    min_reach = abs(
        upper_length
        - lower_length
    )
    reached = (
        min_reach
        <= distance
        <= max_reach
    )
    clamped = min(
        max_reach
        - 1e-12,
        max(
            min_reach
            + 1e-12,
            distance,
        ),
    )
    direction = (
        math.atan2(
            dy,
            dx,
        )
        if distance > 1e-12
        else 0.0
    )
    cosine = (
        (
            upper_length
            * upper_length
            + clamped
            * clamped
            - lower_length
            * lower_length
        )
        / (
            2.0
            * upper_length
            * clamped
        )
    )
    cosine = max(
        -1.0,
        min(
            1.0,
            cosine,
        ),
    )
    offset = (
        math.acos(cosine)
        * bend_sign
    )
    joint_angle = (
        direction
        + offset
    )
    joint_x = (
        root_x
        + math.cos(
            joint_angle
        )
        * upper_length
    )
    joint_y = (
        root_y
        + math.sin(
            joint_angle
        )
        * upper_length
    )
    if reached:
        end_x = target_x
        end_y = target_y
    else:
        target_distance = (
            max_reach
            if distance
            > max_reach
            else min_reach
        )
        end_x = (
            root_x
            + math.cos(
                direction
            )
            * target_distance
        )
        end_y = (
            root_y
            + math.sin(
                direction
            )
            * target_distance
        )
    payload = {
        "era": policy.era.value,
        "joint": (
            round(
                joint_x,
                policy.pose_precision,
            ),
            round(
                joint_y,
                policy.pose_precision,
            ),
        ),
        "end": (
            round(
                end_x,
                policy.pose_precision,
            ),
            round(
                end_y,
                policy.pose_precision,
            ),
        ),
        "reached": reached,
    }
    return IKResult(
        payload["joint"][0],
        payload["joint"][1],
        payload["end"][0],
        payload["end"][1],
        reached,
        _digest(payload),
    )


@dataclass(frozen=True, slots=True)
class AnimationProbe:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class AnimationQualityReport:
    era: EngineEra
    probes: tuple[
        AnimationProbe,
        ...,
    ]

    @property
    def passed(self) -> bool:
        return bool(self.probes) and all(
            probe.passed
            for probe in self.probes
        )

    @property
    def score(self) -> float:
        return sum(
            probe.passed
            for probe in self.probes
        ) / max(
            1,
            len(self.probes),
        )

    @property
    def failed(self) -> tuple[str, ...]:
        return tuple(
            probe.name
            for probe in self.probes
            if not probe.passed
        )


class AnimationAdversary:
    """Attest compiled animation and deterministic playback behavior."""

    def evaluate(
        self,
        sandbox: RoutedEngineSandbox,
        source: AnimationSceneSource,
    ) -> AnimationQualityReport:
        try:
            expected = compile_animation_build(
                sandbox.era,
                source,
            )
            manifest = json.loads(
                sandbox.tree.read(
                    "animation/compiled/manifest.json"
                )
            )
            policy_doc = json.loads(
                sandbox.tree.read(
                    "animation/compiled/policy.json"
                )
            )
        except (
            GameEngineLabError,
            json.JSONDecodeError,
        ) as exc:
            detail = str(exc)
            return AnimationQualityReport(
                sandbox.era,
                tuple(
                    AnimationProbe(
                        name,
                        False,
                        detail,
                    )
                    for name in (
                        "manifest",
                        "inventory",
                        "integrity",
                        "replay",
                        "snapshot",
                        "blend",
                        "root_motion",
                        "ik",
                    )
                ),
            )

        expected_paths = {
            patch.path
            for patch
            in animation_build_patches(
                expected
            )
        }
        actual_paths = {
            path
            for path in sandbox.tree.files
            if path.startswith(
                "animation/compiled/"
            )
        }
        manifest_ok = (
            manifest
            == expected.manifest()
        )
        inventory_ok = (
            expected_paths
            == actual_paths
        )
        integrity_ok = (
            policy_doc
            == _policy_document(
                animation_policy(
                    sandbox.era
                )
            )
        )
        for clip in expected.clips:
            path = (
                "animation/compiled/"
                + clip.clip_id
                + ".clip.json"
            )
            try:
                document = json.loads(
                    sandbox.tree.read(
                        path
                    )
                )
            except (
                GameEngineLabError,
                json.JSONDecodeError,
            ):
                integrity_ok = False
                break
            if document != clip.document():
                integrity_ok = False
                break

        first = HistoricalAnimator(
            sandbox.era,
            source,
        )
        second = HistoricalAnimator(
            sandbox.era,
            source,
        )
        first_poses = (
            first.step(64)
        )
        second_poses = (
            second.step(64)
        )
        replay_ok = (
            first_poses
            == second_poses
            and first.fingerprint()
            == second.fingerprint()
        )

        snapshot_player = (
            HistoricalAnimator(
                sandbox.era,
                source,
            )
        )
        snapshot_player.step(7)
        snapshot = (
            snapshot_player.snapshot()
        )
        before = (
            snapshot_player.fingerprint()
        )
        snapshot_player.step(9)
        snapshot_player.restore(
            snapshot
        )
        snapshot_ok = (
            snapshot_player.fingerprint()
            == before
        )

        policy = animation_policy(
            sandbox.era
        )
        blend_ok = True
        if policy.blending:
            if (
                len(source.clips)
                < 2
            ):
                blend_ok = False
            else:
                blend_player = HistoricalAnimator(
                    sandbox.era,
                    source,
                )
                a = blend_player.blend(
                    source.clips[0].clip_id,
                    source.clips[1].clip_id,
                    0.5,
                    tick=2.0,
                )
                b = blend_player.blend(
                    source.clips[0].clip_id,
                    source.clips[1].clip_id,
                    0.5,
                    tick=2.0,
                )
                blend_ok = (
                    a == b
                )

        root_motion_ok = True
        if policy.root_motion:
            player = HistoricalAnimator(
                sandbox.era,
                source,
            )
            root_clip = next(
                (
                    clip
                    for clip
                    in source.clips
                    if any(
                        track.kind
                        in {
                            TrackKind.ROOT_X,
                            TrackKind.ROOT_Z,
                        }
                        for track
                        in clip.tracks
                    )
                ),
                None,
            )
            if root_clip is None:
                root_motion_ok = False
            else:
                delta = (
                    player.root_motion_delta(
                        root_clip.clip_id,
                        0.0,
                        min(
                            4.0,
                            float(
                                root_clip.duration_ticks
                            ),
                        ),
                    )
                )
                root_motion_ok = all(
                    math.isfinite(
                        value
                    )
                    for value
                    in delta
                )

        ik_ok = True
        if policy.ik:
            first_ik = solve_two_bone_ik(
                sandbox.era,
                root_x=0.0,
                root_y=0.0,
                target_x=1.0,
                target_y=1.0,
                upper_length=1.0,
                lower_length=1.0,
            )
            second_ik = solve_two_bone_ik(
                sandbox.era,
                root_x=0.0,
                root_y=0.0,
                target_x=1.0,
                target_y=1.0,
                upper_length=1.0,
                lower_length=1.0,
            )
            ik_ok = (
                first_ik
                == second_ik
                and first_ik.reached
            )

        return AnimationQualityReport(
            sandbox.era,
            (
                AnimationProbe(
                    "manifest",
                    manifest_ok,
                    "canonical animation manifest",
                ),
                AnimationProbe(
                    "inventory",
                    inventory_ok,
                    "exact compiled animation inventory",
                ),
                AnimationProbe(
                    "integrity",
                    integrity_ok,
                    "compiled clips and policy attested",
                ),
                AnimationProbe(
                    "replay",
                    replay_ok,
                    "deterministic fixed-tick playback",
                ),
                AnimationProbe(
                    "snapshot",
                    snapshot_ok,
                    "playback snapshot roundtrip",
                ),
                AnimationProbe(
                    "blend",
                    blend_ok,
                    "era blend capability",
                ),
                AnimationProbe(
                    "root_motion",
                    root_motion_ok,
                    "era root-motion capability",
                ),
                AnimationProbe(
                    "ik",
                    ik_ok,
                    "era IK capability",
                ),
            ),
        )


def _track(
    target: str,
    kind: TrackKind,
    interpolation: Interpolation,
    *points: tuple[int, float],
) -> AnimationTrack:
    return AnimationTrack(
        target,
        kind,
        interpolation,
        tuple(
            AnimationKeyframe(
                tick,
                value,
            )
            for tick, value
            in points
        ),
    )


def canonical_animation_source(
    era: EngineEra | str,
) -> AnimationSceneSource:
    policy = animation_policy(
        era
    )

    if (
        policy.allowed_tracks
        == SPRITE_TRACKS
    ):
        idle = AnimationClipSource(
            "idle",
            6,
            True,
            (
                _track(
                    "player",
                    TrackKind.SPRITE_INDEX,
                    Interpolation.STEP,
                    (0, 0),
                    (3, 1),
                    (6, 0),
                ),
            ),
        )
        active = AnimationClipSource(
            "active",
            4,
            True,
            (
                _track(
                    "player",
                    TrackKind.SPRITE_INDEX,
                    Interpolation.STEP,
                    (0, 0),
                    (2, 1),
                    (4, 2),
                ),
            ),
        )
        return AnimationSceneSource(
            (
                idle,
                active,
            )
        )

    interpolation = (
        Interpolation.SMOOTH
        if Interpolation.SMOOTH
        in policy.interpolation
        else Interpolation.LINEAR
    )
    idle_tracks = [
        _track(
            "player",
            TrackKind.TRANSLATION_Y,
            interpolation,
            (0, 0.0),
            (4, 0.1),
            (8, 0.0),
        ),
    ]
    move_tracks = [
        _track(
            "player",
            TrackKind.TRANSLATION_X,
            interpolation,
            (0, 0.0),
            (8, 4.0),
        ),
    ]

    if (
        TrackKind.TRANSLATION_Z
        in policy.allowed_tracks
    ):
        move_tracks.append(
            _track(
                "player",
                TrackKind.TRANSLATION_Z,
                interpolation,
                (0, 0.0),
                (8, 1.0),
            )
        )

    if (
        TrackKind.BONE_ROTATION_DEG
        in policy.allowed_tracks
    ):
        idle_tracks.append(
            _track(
                "spine",
                TrackKind.BONE_ROTATION_DEG,
                interpolation,
                (0, -2.0),
                (4, 2.0),
                (8, -2.0),
            )
        )
        move_tracks.append(
            _track(
                "leg_l",
                TrackKind.BONE_ROTATION_DEG,
                interpolation,
                (0, -20.0),
                (4, 20.0),
                (8, -20.0),
            )
        )

    if policy.root_motion:
        move_tracks.extend(
            (
                _track(
                    "root",
                    TrackKind.ROOT_X,
                    interpolation,
                    (0, 0.0),
                    (8, 2.0),
                ),
                _track(
                    "root",
                    TrackKind.ROOT_Z,
                    interpolation,
                    (0, 0.0),
                    (8, 0.5),
                ),
            )
        )

    if policy.ik:
        move_tracks.append(
            _track(
                "foot_l",
                TrackKind.IK_WEIGHT,
                interpolation,
                (0, 0.0),
                (4, 1.0),
                (8, 0.0),
            )
        )

    return AnimationSceneSource(
        (
            AnimationClipSource(
                "idle",
                8,
                True,
                tuple(
                    idle_tracks
                ),
            ),
            AnimationClipSource(
                "move",
                8,
                True,
                tuple(
                    move_tracks
                ),
            ),
        )
    )
