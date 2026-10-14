"""Executable bounded Jeeves/Dragon/adversarial studio learning campaigns.

Campaign budgets are plans; only committed, actually executed rounds advance
cursor. Deterministic specialist checks are not LLM art critics. The existing
application workspace owns authorization, leases, durable rounds and lessons.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import random
import struct
import sys
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .game_learning import (
    GameLearningCancelled,
    GameLearningConfig,
    GameLearningError,
    GamePolicyLearner,
)
from .game_learning_parallel import GameEnvironmentRequest
from .game_style_analysis import MECHANIC_CATALOG, canonical, digest

CAMPAIGN_SCHEMA = "skeleton.game.studio_campaign.v1"
ROUND_SCHEMA = "skeleton.game.studio_round.v1"
LESSON_SCHEMA = "skeleton.game.studio_lesson.v1"
CONTEXT_FIELDS = ("target_id", "genre", "engine", "source_digest", "code_digest")
TRANSFER_FIELDS = ("target_id", "genre", "engine", "code_digest")
PROPOSAL_TRANSFER = "proposal_only_not_measurement"


def _int(value: Any, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise GameLearningError(f"{name} must be an integer within[{low},{high}]")
    return value


def _copy(value: Any, limit: int = 8 * 1024 * 1024) -> Any:
    return json.loads(canonical(value, limit=limit))


def _implementation() -> str:
    names = (
        "game_studio_learning.py",
        "game_learning.py",
        "game_learning_parallel.py",
        "game_successor_runtime.py",
        "game_successor_world.py",
        "game_console_editor.py",
        "game_console_simulation.py",
        "game_emulator_host.py",
    )
    return digest(
        {
            "python": list(sys.version_info[:3]),
            "files": {
                name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                for name in names
                if Path(__file__).with_name(name).is_file()
            },
        }
    )


def _guard(cancel: Callable[[], bool] | None, authorize: Callable[[], None] | None) -> None:
    if cancel is not None and cancel():
        raise GameLearningCancelled("studio campaign slice cancelled")
    if authorize is not None:
        result = authorize()
        if result is False or result is not None and result is not True:
            raise GameLearningError("studio campaign authorization did not finish synchronously")


@dataclass(frozen=True, slots=True)
class CampaignConfig:
    round_limit: int = 100000
    slice_rounds: int = 4
    episodes_per_round: int = 1
    episode_steps: int = 256
    seed: int = 0
    min_improvement: float = 0.0
    max_slice_steps: int = 131072

    def __post_init__(self) -> None:
        _int(self.round_limit, "campaign rounds", 1, 100000)
        _int(self.slice_rounds, "slice rounds", 1, 8)
        _int(self.episodes_per_round, "round training episodes", 1, 4)
        _int(self.episode_steps, "episode steps", 1, 4096)
        _int(self.seed, "campaign seed", 0, 2**63 - 1)
        _int(self.max_slice_steps, "slice step budget", 1, 131072)
        if (
            type(self.min_improvement) not in (int, float)
            or not 0 <= self.min_improvement <= 1000000
            or not math.isfinite(self.min_improvement)
        ):
            raise GameLearningError("minimum improvement must be finite and nonnegative")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_lesson(value: Mapping[str, Any], *, context_digest: str) -> dict[str, Any]:
    raw = _copy(dict(value), 262144)
    required = {
        "schema_version",
        "context_digest",
        "round_index",
        "role",
        "outcome",
        "candidate_digest",
        "facts",
        "recommendation",
        "evidence_digest",
        "lesson_digest",
    }
    if (
        set(raw) != required
        or raw["schema_version"] != LESSON_SCHEMA
        or raw["context_digest"] != context_digest
    ):
        raise GameLearningError("lesson schema or target/genre/engine/source/code scope differs")
    _int(raw["round_index"], "lesson round", 1, 100000)
    if raw["role"] not in ("jeeves", "dragon", "adversary", "decision") or raw["outcome"] not in (
        "accepted",
        "rejected",
    ):
        raise GameLearningError("lesson role/outcome differs")
    unsigned = {k: v for k, v in raw.items() if k != "lesson_digest"}
    if raw["lesson_digest"] != digest(unsigned):
        raise GameLearningError("lesson evidence digest differs")
    for field in ("candidate_digest", "evidence_digest"):
        if (
            not isinstance(raw[field], str)
            or len(raw[field]) != 64
            or any(c not in "0123456789abcdef" for c in raw[field])
        ):
            raise GameLearningError("lesson identity is not SHA-256")
    if (
        not isinstance(raw["facts"], dict)
        or not isinstance(raw["recommendation"], str)
        or len(raw["recommendation"]) > 1024
    ):
        raise GameLearningError("lesson facts/recommendation exceed bounds")
    return raw


def make_proposal_prior(
    lesson: Mapping[str, Any],
    *,
    origin_context: Mapping[str, Any],
    destination_context: Mapping[str, Any],
) -> dict[str, Any]:
    """Preserve issued empirical evidence while proposing across admitted builds.

    The application must reauthorize the historical source and issuing owner.
    This envelope grants no source rights or empirical authority in a new build.
    """
    origin = _copy(dict(origin_context), 65536)
    destination = _copy(dict(destination_context), 65536)
    for context in (origin, destination):
        if not all(isinstance(context.get(k), str) and 1 <= len(context[k]) <= 256 for k in CONTEXT_FIELDS):
            raise GameLearningError("proposal requires explicit original and destination contexts")
        for name in ("source_digest", "code_digest"):
            value = context[name]
            if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise GameLearningError("proposal source/code identity is not SHA-256")
    if any(origin[k] != destination[k] for k in TRANSFER_FIELDS):
        raise GameLearningError("proposal target/genre/engine/code eligibility differs")
    original = validate_lesson(lesson, context_digest=digest(origin))
    raw = {
        "transfer_kind": PROPOSAL_TRANSFER,
        "lesson": original,
        "origin_context": origin,
        "origin_context_digest": digest(origin),
        "destination_context_digest": digest(destination),
        "evidence_digest": original["evidence_digest"],
    }
    raw["prior_digest"] = digest(raw)
    return _copy(raw, 262144)


def validate_proposal_prior(
    value: Mapping[str, Any], *, destination_context: Mapping[str, Any]
) -> dict[str, Any]:
    raw = _copy(dict(value), 262144)
    if set(raw) != {
        "transfer_kind",
        "lesson",
        "origin_context",
        "origin_context_digest",
        "destination_context_digest",
        "evidence_digest",
        "prior_digest",
    }:
        raise GameLearningError("proposal prior schema differs")
    expected = make_proposal_prior(
        raw["lesson"],
        origin_context=raw["origin_context"],
        destination_context=destination_context,
    )
    if raw != expected:
        raise GameLearningError("proposal prior original evidence or destination binding differs")
    return raw


class StudioLearningCampaign:
    """Episode-bounded optimization with an atomic committed-round protocol."""

    def __init__(
        self,
        request: GameEnvironmentRequest,
        config: CampaignConfig,
        context: Mapping[str, Any],
        lineage: Mapping[str, Any],
        policy_snapshot: Mapping[str, Any] | None = None,
        snapshot: Mapping[str, Any] | None = None,
        lessons: Sequence[Mapping[str, Any]] = (),
        proposal_priors: Sequence[Mapping[str, Any]] = (),
    ) -> None:
        if not isinstance(request, GameEnvironmentRequest) or not isinstance(config, CampaignConfig):
            raise GameLearningError("typed studio request/config required")
        execution = request.as_dict()
        execution["max_steps"] = config.episode_steps
        request = GameEnvironmentRequest.from_dict(execution)
        self.request, self.config = request, config
        self.context = _copy(dict(context), 65536)
        if not all(
            isinstance(self.context.get(k), str) and 1 <= len(self.context[k]) <= 256 for k in CONTEXT_FIELDS
        ):
            raise GameLearningError("explicit target/genre/engine/source/code context required")
        if self.context["target_id"] != request.target_id:
            raise GameLearningError("campaign target differs from execution request")
        for name in ("source_digest", "code_digest"):
            value = self.context[name]
            if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise GameLearningError("campaign source/code identity is not SHA-256")
        self.context_digest = digest(self.context)
        if len(proposal_priors) > 128:
            raise GameLearningError("proposal prior count exceeds128")
        self.proposal_priors = [
            validate_proposal_prior(v, destination_context=self.context) for v in proposal_priors
        ]
        _copy(self.proposal_priors, 262144)
        if len({v["prior_digest"] for v in self.proposal_priors}) != len(self.proposal_priors):
            raise GameLearningError("duplicate proposal prior")
        self.lineage = _copy(dict(lineage), 65536)
        if not self.lineage or self.lineage.get("rights_acknowledged") is False:
            raise GameLearningError("explicit admitted source lineage required")
        self.implementation_digest = _implementation()
        self.binding = {
            "request_digest": request.digest,
            "config": config.as_dict(),
            "context_digest": self.context_digest,
            "lineage_digest": digest(self.lineage),
            "implementation_digest": self.implementation_digest,
            "proposal_priors_digest": digest(self.proposal_priors),
        }
        self.campaign_id = "studio-" + digest(self.binding)[:40]
        self.cursor = 0
        self.cumulative_steps = 0
        self.champion = request
        self.champion_policy = None if policy_snapshot is None else _copy(policy_snapshot)
        self.history_digest = digest({"campaign_id": self.campaign_id, "genesis": self.binding})
        self.last_round_digest = None
        self.lesson_count = 0
        self.recent_lessons = []
        if len(lessons) > 128:
            raise GameLearningError("imported lesson count exceeds128")
        seen = set()
        for value in lessons:
            lesson = validate_lesson(value, context_digest=self.context_digest)
            if lesson["lesson_digest"] in seen:
                raise GameLearningError("duplicate imported lesson")
            seen.add(lesson["lesson_digest"])
            self.recent_lessons.append(lesson)
        self.recent_lessons = self.recent_lessons[-64:]
        if snapshot is not None:
            self._restore(snapshot)
        self._validate_policy(self.champion, self.champion_policy)
        self._executing = False
        self._lock = threading.Lock()

    @staticmethod
    def _spec(request: GameEnvironmentRequest):
        env = request.build()
        try:
            return env.spec
        finally:
            close = getattr(env, "close", None)
            if callable(close):
                close()

    def _validate_policy(self, request, policy):
        if policy is not None:
            GamePolicyLearner.from_snapshot(policy, expected_spec=self._spec(request))

    def snapshot(self) -> dict[str, Any]:
        raw = {
            "schema_version": CAMPAIGN_SCHEMA,
            "campaign_id": self.campaign_id,
            "binding": self.binding,
            "cursor": self.cursor,
            "round_limit": self.config.round_limit,
            "cumulative_steps": self.cumulative_steps,
            "champion_request": self.champion.as_dict(),
            "champion_request_digest": self.champion.digest,
            "champion_policy": self.champion_policy,
            "champion_policy_digest": (
                None if self.champion_policy is None else self.champion_policy["snapshot_digest"]
            ),
            "history_digest": self.history_digest,
            "last_round_digest": self.last_round_digest,
            "lesson_count": self.lesson_count,
            "recent_lessons": self.recent_lessons,
            "proposal_priors": self.proposal_priors,
        }
        raw["snapshot_digest"] = digest(raw)
        return _copy(raw)

    def _restore(self, value):
        raw = _copy(dict(value))
        expected = {
            "schema_version",
            "campaign_id",
            "binding",
            "cursor",
            "round_limit",
            "cumulative_steps",
            "champion_request",
            "champion_request_digest",
            "champion_policy",
            "champion_policy_digest",
            "history_digest",
            "last_round_digest",
            "lesson_count",
            "recent_lessons",
            "proposal_priors",
            "snapshot_digest",
        }
        if (
            set(raw) != expected
            or raw["schema_version"] != CAMPAIGN_SCHEMA
            or raw["campaign_id"] != self.campaign_id
            or raw["binding"] != self.binding
        ):
            raise GameLearningError("campaign snapshot/source/code/config binding differs")
        if raw["snapshot_digest"] != digest({k: v for k, v in raw.items() if k != "snapshot_digest"}):
            raise GameLearningError("campaign snapshot digest differs")
        if raw["proposal_priors"] != self.proposal_priors:
            raise GameLearningError("campaign proposal provenance differs")
        self.cursor = _int(raw["cursor"], "campaign cursor", 0, self.config.round_limit)
        if raw["round_limit"] != self.config.round_limit:
            raise GameLearningError("campaign round admission differs")
        self.cumulative_steps = _int(raw["cumulative_steps"], "campaign actual steps", 0, 100000 * 8 * 4096)
        self.lesson_count = _int(raw["lesson_count"], "campaign lessons", 0, 400000)
        champion = GameEnvironmentRequest.from_dict(raw["champion_request"])
        if (
            champion.target_id != self.request.target_id
            or champion.kind != self.request.kind
            or champion.digest != raw["champion_request_digest"]
        ):
            raise GameLearningError("champion target/request identity differs")
        if (
            self.request.kind not in ("successor", "console_editor")
            and champion.digest != self.request.digest
        ):
            raise GameLearningError(
                "read-only native/reference campaign cannot substitute its admitted source"
            )
        # An admitted rematerialized native root is operational, not semantic.
        self.champion = self.request if champion.digest == self.request.digest else champion
        self.champion_policy = raw["champion_policy"]
        actual = None if self.champion_policy is None else self.champion_policy.get("snapshot_digest")
        if actual != raw["champion_policy_digest"]:
            raise GameLearningError("champion policy identity differs")
        if not isinstance(raw["recent_lessons"], list) or len(raw["recent_lessons"]) > 64:
            raise GameLearningError("campaign recent lesson memory exceeds64")
        self.recent_lessons = [
            validate_lesson(v, context_digest=self.context_digest) for v in raw["recent_lessons"]
        ]
        if len({v["lesson_digest"] for v in self.recent_lessons}) != len(self.recent_lessons):
            raise GameLearningError("campaign recent lesson identities duplicate")
        for field in ("history_digest", "last_round_digest"):
            value = raw[field]
            if value is None and field == "last_round_digest" and self.cursor == 0:
                continue
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(c not in "0123456789abcdef" for c in value)
            ):
                raise GameLearningError("campaign history identity differs")
        self.history_digest, self.last_round_digest = raw["history_digest"], raw["last_round_digest"]

    def _seed(self, index, role):
        return int.from_bytes(
            hashlib.sha256(f"{self.config.seed}:{index}:{role}".encode()).digest()[:8], "big"
        ) % (2**63)

    def _decision(self, mechanic, *, proposed_value=None):
        own = [
            v
            for v in self.recent_lessons
            if v["role"] == "decision" and v["facts"].get("mechanic") == mechanic
        ]
        priors = [
            v
            for v in self.proposal_priors
            if v["lesson"]["role"] == "decision" and v["lesson"]["facts"].get("mechanic") == mechanic
        ]
        candidates = [(v, None) for v in own] if own else [(v["lesson"], v) for v in priors]
        if proposed_value is not None:
            rejected = [
                pair
                for pair in candidates
                if pair[0]["outcome"] == "rejected"
                and any(
                    isinstance(c, dict) and c.get("after") == proposed_value
                    for c in pair[0]["facts"].get("candidate_changes", [])
                )
            ]
            if rejected:
                return rejected[-1]
        return (None, None) if not candidates else candidates[-1]

    @staticmethod
    def _proposal_facts(prior):
        return (
            {}
            if prior is None
            else {
                "proposal_prior_digest": prior["prior_digest"],
                "proposal_origin_context_digest": prior["origin_context_digest"],
                "proposal_evidence_digest": prior["evidence_digest"],
                "transfer_kind": PROPOSAL_TRANSFER,
            }
        )

    def _mutate(self, index):
        rng = random.Random(self._seed(index, "mutation"))
        request = self.champion
        tree = dict(request.tree or {})
        facts = {"supported": False, "strategy": "play_only_opaque_or_unsupported_source", "changes": []}
        if request.kind == "successor":
            from .game_successor_runtime import emit_successor_project

            spec = json.loads(tree["game/successor/spec.json"])
            if index % 6 == 0:
                profiles = ("pixel", "enhanced", "cinematic")
                old = spec.get("fidelity", {"profile": "pixel"})["profile"]
                new = profiles[min(2, profiles.index(old) + 1)]
                decision, prior = self._decision("fidelity.profile", proposed_value=new)
                repeated = (
                    decision is not None
                    and decision["outcome"] == "rejected"
                    and any(
                        isinstance(c, dict) and c.get("after") == new
                        for c in decision["facts"].get("candidate_changes", [])
                    )
                )
                if new != old and not repeated:
                    spec["fidelity"] = {"profile": new}
                    tree.update(emit_successor_project(spec))
                    facts = {
                        "supported": True,
                        "strategy": "measured_progressive_renderer_trial",
                        "mechanic": "fidelity.profile",
                        "changes": [{"path": "fidelity.profile", "before": old, "after": new}],
                        "subjective_quality_improvement_claim": False,
                        **self._proposal_facts(prior),
                    }
                else:
                    facts = {
                        "supported": False,
                        "strategy": "remembered_fidelity_rejection_or_highest_profile",
                        "mechanic": "fidelity.profile",
                        "changes": [],
                        "subjective_quality_improvement_claim": False,
                        **self._proposal_facts(prior),
                    }
            else:
                fields = (
                    "movement.max_speed",
                    "movement.acceleration",
                    "combat.cooldown",
                    "fishing.reel_speed",
                    "farming.day_seconds",
                )
                path = fields[(index - 1) % len(fields)]
                group, key = path.split(".")
                old = spec["mechanics"][group][key]
                direction = 1 if rng.random() >= 0.5 else -1
                decision, prior = self._decision(path)
                if (
                    decision is not None
                    and type(decision["facts"].get("direction")) is int
                    and decision["facts"]["direction"] in (-1, 1)
                ):
                    known = decision["facts"]["direction"]
                    direction = -known if decision["outcome"] == "rejected" else known
                low, high, _, _, _ = MECHANIC_CATALOG[path]
                new = max(low, min(high, old * (1 + direction * 0.05)))
                spec["mechanics"][group][key] = new
                tree.update(emit_successor_project(spec))
                facts = {
                    "supported": True,
                    "strategy": "lesson_guided_bounded_numeric_mutation",
                    "mechanic": path,
                    "direction": direction,
                    "changes": [{"path": path, "before": old, "after": new}],
                    **self._proposal_facts(prior),
                }
        elif request.kind == "console_editor":
            from .game_console_editor import ConsoleProject

            project = ConsoleProject.from_files(tree, target_id=request.target_id)
            document = project.as_dict()
            old = document["config"]["speed"]
            direction = 1 if rng.random() >= 0.5 else -1
            decision, prior = self._decision("config.speed")
            if (
                decision is not None
                and type(decision["facts"].get("direction")) is int
                and decision["facts"]["direction"] in (-1, 1)
            ):
                known = decision["facts"]["direction"]
                direction = -known if decision["outcome"] == "rejected" else known
            new = max(1, min(600, old * (1 + direction * 0.05)))
            document["config"]["speed"] = new
            tree = ConsoleProject(document, tree).export_files()
            facts = {
                "supported": True,
                "strategy": "typed_editor_speed_mutation",
                "mechanic": "config.speed",
                "direction": direction,
                "changes": [{"path": "config.speed", "before": old, "after": new}],
                **self._proposal_facts(prior),
            }
        if facts["supported"]:
            raw = request.as_dict()
            raw["tree"] = tree
            request = GameEnvironmentRequest.from_dict(raw)
        return request, facts

    def _play(self, request, seed, policy, *, jitter, cancel, authorize):
        _guard(cancel, authorize)
        env = request.build(cancel=cancel)
        try:
            observation = env.reset(seed)
            controller = None if policy is None else GamePolicyLearner.from_snapshot(policy)
            if controller is not None:
                before = controller.descriptor
                after = env.spec.as_dict()
                if any(before[k] != after[k] for k in ("actions", "observation_bins", "reward_components")):
                    raise GameLearningError("frozen policy transfer changed action/bin/reward semantics")
            rng = random.Random(seed ^ 0xA0761D6478BD642F)
            total = 0.0
            steps = 0
            actions = {}
            first = env.preview() if hasattr(env, "preview") else None
            for sequence in range(1, self.config.episode_steps + 1):
                _guard(cancel, authorize)
                action = (
                    env.spec.actions[rng.randrange(len(env.spec.actions))]
                    if controller is None
                    else controller.predict(observation)["action"]
                )
                if jitter and sequence % 11 == 0:
                    action = env.spec.actions[rng.randrange(len(env.spec.actions))]
                step = env.step(action)
                observation = step.observation
                total += step.reward
                steps += 1
                actions[action] = actions.get(action, 0) + 1
                if step.terminated or step.truncated:
                    break
            last = env.preview() if hasattr(env, "preview") else None
            info = dict(step.info)
            return {
                "seed": seed,
                "environment_digest": env.spec.environment_digest,
                "policy_digest": None if policy is None else policy["snapshot_digest"],
                "controller": "seeded_random" if controller is None else "frozen_q_policy",
                "input_perturbation": "one_random_action_every11steps" if jitter else "none",
                "steps": steps,
                "return": total,
                "actions": actions,
                "won": info.get("won") is True or info.get("success") is True,
                "dead": info.get("dead") is True,
                "first_frame": self._frame(first),
                "last_frame": self._frame(last),
            }
        finally:
            close = getattr(env, "close", None)
            if callable(close):
                close()

    @staticmethod
    def _frame(frame):
        if frame is None:
            return {"available": False}
        if not isinstance(frame, Mapping):
            raise GameLearningError("actual frame projection differs")
        uri = frame.get("data_uri")
        if not isinstance(uri, str) or not uri.startswith("data:image/png;base64,"):
            return {"available": False, "reason": "no_supported_png_projection"}
        if len(uri) > 700000:
            raise GameLearningError("actual frame exceeds bounded preview bytes")
        try:
            raw = base64.b64decode(uri.split(",", 1)[1], validate=True)
        except ValueError as exc:
            raise GameLearningError("actual frame base64 differs") from exc
        if len(raw) > 524288 or len(raw) < 33 or raw[:8] != b"\x89PNG\r\n\x1a\n":
            raise GameLearningError("actual frame PNG boundary differs")
        width, height = struct.unpack("!II", raw[16:24])
        if not 1 <= width <= 2048 or not 1 <= height <= 2048 or width * height > 1048576:
            raise GameLearningError("actual preview raster dimensions exceed bounds")
        actual = hashlib.sha256(raw).hexdigest()
        if frame.get("png_digest") not in (None, actual):
            raise GameLearningError("actual preview receipt differs")
        from .game_console_assets import decode_png

        decoded_width, decoded_height, pixels = decode_png(raw)
        if (decoded_width, decoded_height) != (width, height):
            raise GameLearningError("actual preview decoded dimensions differ")
        stride = max(1, math.ceil(math.sqrt(width * height / 65536)))
        palette = [0] * 4096
        luminance = [0] * 256
        sampled = opaque = edge_pairs = edges = 0
        previous_row = []
        for y in range(0, height, stride):
            row = []
            for x in range(0, width, stride):
                offset = (y * width + x) * 4
                r, g, b, alpha = pixels[offset : offset + 4]
                sampled += 1
                if alpha >= 16:
                    opaque += 1
                    palette[(r >> 4) * 256 + (g >> 4) * 16 + (b >> 4)] += 1
                    value = (54 * r + 183 * g + 19 * b) >> 8
                    luminance[value] += 1
                else:
                    value = 0
                if row:
                    edge_pairs += 1
                    edges += abs(value - row[-1]) >= 12
                if previous_row:
                    edge_pairs += 1
                    edges += abs(value - previous_row[len(row)]) >= 12
                row.append(value)
            previous_row = row
        occupied = sum(count > 0 for count in palette)
        levels = [index for index, count in enumerate(luminance) if count]
        contrast = 0 if not levels else levels[-1] - levels[0]
        dominant = 1.0 if not opaque else max(palette) / opaque
        edge_density = edges / max(1, edge_pairs)
        visual = {
            "sampled_pixels": sampled,
            "opaque_fraction": opaque / max(1, sampled),
            "occupied_quantized_palette_bins": occupied,
            "palette_capacity": 4096,
            "luminance_range": contrast,
            "dominant_color_fraction": dominant,
            "edge_density": edge_density,
            "sample_stride": stride,
            "flat_raster": occupied < 2 or contrast < 4,
            "readable_signal": opaque / max(1, sampled) >= 0.02
            and occupied >= 2
            and contrast >= 4
            and dominant <= 0.999
            and edge_density >= 0.0001,
            "classification": "actual_bounded_pixel_statistics_not_subjective_aesthetics",
        }
        return {
            "available": True,
            "width": width,
            "height": height,
            "png_bytes": len(raw),
            "png_digest": actual,
            "pixel_digest": frame.get("pixel_digest"),
            "art_digest": frame.get("art_digest"),
            "fidelity": _copy(frame.get("fidelity"), 2048),
            "visual_metrics": visual,
            "classification": "measured_raster_identity_and_dimensions_not_subjective_art_quality",
        }

    def _dragon(self, request, play):
        tree = request.tree or {}
        size = sum(len(v.encode()) for v in tree.values())
        checks = {
            "source_request_digest": request.digest,
            "project_bytes": size,
            "bounded_project": size <= 4 * 1024 * 1024,
            "actual_frame_available": play["last_frame"]["available"],
            "source_lineage_digest": digest(self.lineage),
            "originality": (
                "original_authored_successor"
                if request.kind == "successor"
                else "source_owner_admitted_content_not_semantic_originality_proof"
            ),
            "model_critic_executed": False,
            "visual_metrics": play["last_frame"].get("visual_metrics"),
        }
        if request.kind == "successor":
            from .game_successor import validate_successor_routes

            checks["layout"] = validate_successor_routes(json.loads(tree["game/successor/spec.json"]))
        elif request.kind == "console_editor":
            from .game_console_editor import ConsoleProject, inspect_console_project

            project = ConsoleProject.from_files(tree, target_id=request.target_id)
            report = inspect_console_project(project)
            checks["layout"] = {
                "document_digest": project.digest,
                "validation": report,
                "classification": "typed_source_capacity_rules_not_hardware_execution_proof",
            }
        else:
            checks["layout"] = {
                "available": False,
                "reason": "opaque_native_source_not_automatically_rewritten",
            }
        checks["passed"] = (
            checks["bounded_project"]
            and checks["actual_frame_available"]
            and bool((checks["visual_metrics"] or {}).get("readable_signal"))
        )
        checks["report_digest"] = digest(checks)
        return checks

    def _round(self, index, cancel, authorize):
        _guard(cancel, authorize)
        if _implementation() != self.implementation_digest:
            raise GameLearningError("studio implementation changed during campaign")
        candidate, mutation = self._mutate(index)
        candidate_spec = self._spec(candidate)
        model = GamePolicyLearner(
            candidate_spec,
            GameLearningConfig(
                seed=self._seed(index, "q"),
                max_updates=max(1, self.config.episodes_per_round * self.config.episode_steps),
                max_episodes=self.config.episodes_per_round,
                max_states=4096,
            ),
            policy_id=f"{self.campaign_id}-r{index}",
            source_lineage=self.lineage,
        )
        training_seeds = tuple(self._seed(index, f"train-{i}") for i in range(self.config.episodes_per_round))
        if len(set(training_seeds)) != len(training_seeds):
            raise GameLearningError("campaign training seed collision")
        trained = model.train(
            lambda: candidate.build(cancel=cancel),
            episodes=self.config.episodes_per_round,
            seeds=training_seeds,
            cancel=cancel,
            authorize=authorize,
        )
        policy = trained.snapshot
        ordinary_seed = self._seed(index, "heldout")
        jitter_seed = self._seed(index, "adversarial")
        if ordinary_seed == jitter_seed or {ordinary_seed, jitter_seed} & set(training_seeds):
            raise GameLearningError("campaign seed partitions collide")
        baseline = self._play(
            self.champion,
            ordinary_seed,
            self.champion_policy,
            jitter=False,
            cancel=cancel,
            authorize=authorize,
        )
        measured = self._play(
            candidate, ordinary_seed, policy, jitter=False, cancel=cancel, authorize=authorize
        )
        baseline_adv = self._play(
            self.champion, jitter_seed, self.champion_policy, jitter=True, cancel=cancel, authorize=authorize
        )
        measured_adv = self._play(
            candidate, jitter_seed, policy, jitter=True, cancel=cancel, authorize=authorize
        )
        dragon = self._dragon(candidate, measured)
        improvement = measured["return"] - baseline["return"]
        adversarial_delta = measured_adv["return"] - baseline_adv["return"]
        accepted = (
            dragon["passed"]
            and improvement > max(1e-9, self.config.min_improvement)
            and adversarial_delta >= -1e-9
            and not (measured["dead"] and not baseline["dead"])
        )
        steps = trained.updates + sum(v["steps"] for v in (baseline, measured, baseline_adv, measured_adv))
        roles = {
            "jeeves": {
                "actual_training_episodes": self.config.episodes_per_round,
                "actual_updates": trained.updates,
                "policy_digest": policy["snapshot_digest"],
                "training_seeds": list(training_seeds),
                "play": measured,
                "champion_play": baseline,
                "fresh_candidate_policy": True,
            },
            "dragon": dragon,
            "adversary": {
                "seed": jitter_seed,
                "candidate": measured_adv,
                "champion": baseline_adv,
                "actual_return_delta": adversarial_delta,
                "semantic_generalization_claim": False,
            },
        }
        for name, evidence in roles.items():
            if "report_digest" not in evidence:
                evidence["report_digest"] = digest({"role": name, "evidence": evidence})
        raw = {
            "schema_version": ROUND_SCHEMA,
            "campaign_id": self.campaign_id,
            "round_index": index,
            "context_digest": self.context_digest,
            "previous_history_digest": self.history_digest,
            "candidate_digest": candidate.digest,
            "champion_before_digest": self.champion.digest,
            "mutation": mutation,
            "roles": roles,
            "actual_steps": steps,
            "status": "accepted" if accepted else "rejected",
            "champion_promoted": accepted,
            "decision": {
                "ordinary_return_delta": improvement,
                "adversarial_return_delta": adversarial_delta,
                "minimum_improvement": self.config.min_improvement,
                "hard_checks_passed": dragon["passed"],
                "gameplay_gain_is_not_an_aesthetic_score": True,
                "reason": (
                    "measured_ordinary_gain_and_no_perturbed_regression"
                    if accepted
                    else "candidate_failed_one_or_more_declared_gates"
                ),
            },
            "proposals": [],
            "lessons": [],
            "implementation_digest": self.implementation_digest,
        }
        evidence_digest = digest(roles)
        for role in ("jeeves", "dragon", "adversary", "decision"):
            facts = {
                "actual_steps": steps,
                "ordinary_return_delta": improvement,
                "adversarial_return_delta": adversarial_delta,
                "mechanic": mutation.get("mechanic"),
                "direction": mutation.get("direction"),
                "candidate_changes": mutation["changes"],
            }
            lesson = {
                "schema_version": LESSON_SCHEMA,
                "context_digest": self.context_digest,
                "round_index": index,
                "role": role,
                "outcome": raw["status"],
                "candidate_digest": candidate.digest,
                "facts": facts,
                "recommendation": (
                    "Retain this measured candidate within the exact admitted context."
                    if accepted
                    else "Avoid repeating this parameter direction without new evidence; champion retained."
                ),
                "evidence_digest": evidence_digest,
            }
            lesson["lesson_digest"] = digest(lesson)
            raw["lessons"].append(lesson)
        if accepted and mutation["supported"]:
            raw["proposals"] = [
                {
                    "operation": "project_compile",
                    "target_id": candidate.target_id,
                    "request_digest": candidate.digest,
                    "status": "requires_existing_scoped_build_tool_execution",
                    "successful_build_claim": False,
                }
            ]
        raw["round_digest"] = digest(raw)
        return _copy(raw, 262144), candidate, policy

    def run_slice(self, rounds: int, *, on_checkpoint=None, authorize=None, cancel=None) -> dict[str, Any]:
        if not self._lock.acquire(blocking=False):
            raise GameLearningError("campaign already executing a slice")
        try:
            return self._run_slice(rounds, on_checkpoint=on_checkpoint, authorize=authorize, cancel=cancel)
        finally:
            self._lock.release()

    def _run_slice(
        self,
        rounds: int,
        *,
        on_checkpoint: Callable[[dict[str, Any], dict[str, Any]], None] | None = None,
        authorize: Callable[[], None] | None = None,
        cancel: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        count = _int(rounds, "requested actual slice rounds", 1, self.config.slice_rounds)
        if self._executing:
            raise GameLearningError("campaign already executing a slice")
        if self.cursor + count > self.config.round_limit:
            raise GameLearningError("campaign requested beyond admitted total round budget")
        planned = count * (self.config.episodes_per_round + 4) * self.config.episode_steps
        if planned > self.config.max_slice_steps:
            raise GameLearningError("campaign planned slice exceeds cumulative step budget")
        _guard(cancel, authorize)
        self._executing = True
        reports = []
        actual = 0
        try:
            for _ in range(count):
                previous = self.snapshot()
                report, candidate, policy = self._round(self.cursor + 1, cancel, authorize)
                _guard(cancel, authorize)
                if _implementation() != self.implementation_digest:
                    raise GameLearningError("studio code changed before round commit")
                try:
                    self.cursor += 1
                    self.cumulative_steps += report["actual_steps"]
                    actual += report["actual_steps"]
                    self.lesson_count += len(report["lessons"])
                    self.recent_lessons = (self.recent_lessons + report["lessons"])[-64:]
                    self.history_digest = digest(
                        {"previous": self.history_digest, "round_digest": report["round_digest"]}
                    )
                    self.last_round_digest = report["round_digest"]
                    if report["champion_promoted"]:
                        self.champion, self.champion_policy = candidate, policy
                    committed = self.snapshot()
                    if on_checkpoint is not None:
                        on_checkpoint(committed, report)
                except BaseException:
                    self._restore(previous)
                    raise
                reports.append(report)
            return {
                "snapshot": self.snapshot(),
                "rounds": reports,
                "actual_rounds": len(reports),
                "actual_steps": actual,
                "planned_steps": planned,
                "remaining_rounds": self.config.round_limit - self.cursor,
                "status": (
                    "completed" if self.cursor == self.config.round_limit else "paused_between_bounded_slices"
                ),
            }
        finally:
            self._executing = False
