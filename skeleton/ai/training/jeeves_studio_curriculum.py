"""Replay-verified original-engine experience for checkpoint-derived Jeeves training.

Only source-authoritative runtime transitions produce model text. The fixed
Pareto holdout remains separate; this producer provides *training-only*
experience. An operator independently pins the serialized file SHA before
admitting it to the live-checkpoint candidate trainer. No arbitrary source
text or unverified game result enters the neural optimizer.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any

from skeleton.jeeves.game_studio_environment import (
    make_studio_source, parse_studio_source, studio_request_tree,
)
from skeleton.jeeves.game_learning_parallel import GameEnvironmentRequest

SCHEMA = "skeleton.jeeves.studio_training_corpus.v1"
MAX_BYTES = 2 * 1024 * 1024
MAX_EXAMPLES = 256


class StudioCurriculumError(ValueError):
    """Missing source, replay evidence, bounds or rights admission."""


def _canonical(value):
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError, OverflowError) as exc:
        raise StudioCurriculumError("studio evidence must be canonical finite JSON") from exc
    if len(raw) > MAX_BYTES:
        raise StudioCurriculumError("studio learning corpus exceeds byte budget")
    return raw


def _sha(value):
    return sha256(_canonical(value)).hexdigest()


def _scalar(value):
    if type(value) not in (int, float):
        raise StudioCurriculumError("projected observation must be real numeric state")
    return f"{value:.3f}"


def _text(editor, action, before, after, reward, accepted):
    # This is an observed state-transition summary, not an authored gameplay
    # goal or hallucinated quality annotation. Valid action != good strategy.
    basis = [
        "Original playable engine " + editor + ".",
        "Observed progress " + _scalar(before["progress"])
        + " to " + _scalar(after["progress"]) + ".",
        "Observed score " + _scalar(before["score"])
        + " to " + _scalar(after["score"]) + ".",
        "Observed health " + _scalar(before["health"])
        + " to " + _scalar(after["health"]) + ".",
        "Executed action " + action + " was "
        + ("accepted." if accepted else "rejected."),
        "Local utility reward " + _scalar(reward) + ".",
        "Jeeves: Describe the observed state change and avoid inventing a goal.",
    ]
    return " ".join(basis)


def _run_episode(source, item):
    if type(item) is not dict or set(item) != {"seed", "actions"}:
        raise StudioCurriculumError("exact original episode input required")
    seed, actions = item["seed"], item["actions"]
    if type(seed) is not int or not 0 <= seed <= 2**63 - 1:
        raise StudioCurriculumError("invalid episode seed")
    if type(actions) is not list or not 1 <= len(actions) <= 128:
        raise StudioCurriculumError("bounded game episode action log required")
    if any(type(action) is not str or action not in source["actions"] for action in actions):
        raise StudioCurriculumError("unapproved game command in corpus")
    request = GameEnvironmentRequest(
        "studio:" + source["editor"], kind="studio", max_steps=len(actions),
        tree=studio_request_tree(source),
    )
    env = request.build()
    examples = []
    evidence = []
    try:
        before = dict(env.reset(seed))
        initial_digest = env.snapshot()["source_session_digest"]
        for action in actions:
            if env.done:
                raise StudioCurriculumError("recorded game commands continue after terminal event")
            measured = env.step(action)
            after = dict(measured.observation)
            accepted = bool(measured.info["evidence"]["accepted"])
            examples.append(_text(source["editor"], action, before, after,
                                  measured.reward, accepted))
            evidence.append(measured.transition_digest)
            before = after
        ending = env.snapshot()
        return {
            "seed": seed, "actions": list(actions), "examples": examples,
            "initial_digest": initial_digest,
            "terminal_digest": ending["source_session_digest"],
            "environment_digest": env.spec.environment_digest,
            "transition_digests": evidence,
            "actual_gameplay_steps": len(actions),
            "native_hardware_verified": False,
        }
    finally:
        env.close()


def build_studio_curriculum(source: dict[str, object], episodes: list[dict[str, object]],
                            *, authorized: bool, rights_cleared: bool) -> dict[str, object]:
    if authorized is not True or rights_cleared is not True:
        raise PermissionError("model-training source needs operator approval and rights clearance")
    original = parse_studio_source(source)
    if type(episodes) is not list or not 1 <= len(episodes) <= 32:
        raise StudioCurriculumError("studio corpus episode budget exceeded")
    normalized = []
    seen = set()
    for item in episodes:
        recorded = _run_episode(original, item)
        if recorded["seed"] in seen:
            raise StudioCurriculumError("duplicate world seed would overweight a single example")
        seen.add(recorded["seed"])
        normalized.append(recorded)
    if sum(e["actual_gameplay_steps"] for e in normalized) > MAX_EXAMPLES:
        raise StudioCurriculumError("training examples exceed measured sample budget")
    record = {
        "schema_version": SCHEMA,
        "source": original,
        "source_digest": _sha(original),
        "episodes": normalized,
        "rights_acknowledged": True,
        "training_only": True,
        "independent_holdout_supplied": False,
        "live_production_model_modified": False,
        "source_text_untrusted_for_actions": True,
    }
    _canonical(record)
    return {**record, "digest": _sha(record)}


def verify_studio_curriculum(document: object) -> tuple[str, ...]:
    if type(document) is not dict or set(document) != {
        "schema_version", "source", "source_digest", "episodes", "rights_acknowledged",
        "training_only", "independent_holdout_supplied",
        "live_production_model_modified", "source_text_untrusted_for_actions", "digest",
    } or document["schema_version"] != SCHEMA:
        raise StudioCurriculumError("exact original game training corpus format required")
    if (document["rights_acknowledged"] is not True
            or document["training_only"] is not True
            or document["independent_holdout_supplied"] is not False
            or document["live_production_model_modified"] is not False
            or document["source_text_untrusted_for_actions"] is not True):
        raise StudioCurriculumError("training corpus claims unauthorized effects")
    if _sha({k:v for k,v in document.items() if k != "digest"}) != document["digest"]:
        raise StudioCurriculumError("studio corpus content digest differs")
    original = parse_studio_source(document["source"])
    if _sha(original) != document["source_digest"]:
        raise StudioCurriculumError("original scene/source identity differs")
    if type(document["episodes"]) is not list or not 1 <= len(document["episodes"]) <= 32:
        raise StudioCurriculumError("source episode list outside capacity")
    actual = build_studio_curriculum(
        original,
        [{"seed": e["seed"], "actions": e["actions"]}
         for e in document["episodes"] if isinstance(e, dict)],
        authorized=True, rights_cleared=True,
    )
    if actual != document:
        raise StudioCurriculumError("independently replayed engine states and labels differ")
    return tuple(label for entry in actual["episodes"] for label in entry["examples"])


def load_studio_curriculum(path: Path, *, expected_sha256: str) -> tuple[tuple[str, ...], str]:
    if (not isinstance(expected_sha256, str) or len(expected_sha256) != 64
            or any(c not in "0123456789abcdef" for c in expected_sha256)):
        raise StudioCurriculumError("independently pinned corpus SHA256 required")
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not 1 <= path.stat().st_size <= MAX_BYTES:
        raise StudioCurriculumError("training input must be a bounded regular file")
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != expected_sha256:
        raise StudioCurriculumError("studio corpus differs from independently pinned bytes")
    def reject_dupes(pairs):
        result={}
        for key,value in pairs:
            if key in result:
                raise StudioCurriculumError("duplicate serialized evidence field")
            result[key]=value
        return result
    try:
        document = json.loads(raw, object_pairs_hook=reject_dupes,
                              parse_constant=lambda _: (_ for _ in ()).throw(
                                  StudioCurriculumError("nonfinite evidence number")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioCurriculumError("invalid serialized original corpus") from exc
    return verify_studio_curriculum(document), expected_sha256


def publish_corpus(path: Path, document: dict[str, object]) -> str:
    verify_studio_curriculum(document)
    raw=_canonical(document)
    target=Path(path).expanduser().absolute()
    if target.is_symlink() or not target.parent.is_dir():
        raise StudioCurriculumError("corpus destination parent must exist")
    fd=os.open(target, os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,"wb") as writer:
            writer.write(raw)
            writer.flush()
            os.fsync(writer.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return sha256(raw).hexdigest()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine",required=True)
    parser.add_argument("--settings-json")
    parser.add_argument("--actions",nargs="+",required=True)
    parser.add_argument("--seed",type=int,default=0)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--authorized",action="store_true")
    parser.add_argument("--rights-cleared",action="store_true")
    args=parser.parse_args(argv)
    source=make_studio_source(
        args.engine, json.loads(args.settings_json) if args.settings_json else None,
        actions=tuple(dict.fromkeys(args.actions)),
    )
    bundle=build_studio_curriculum(
        source,[{"seed":args.seed,"actions":args.actions}],
        authorized=args.authorized,rights_cleared=args.rights_cleared,
    )
    digest=publish_corpus(args.output,bundle)
    print(json.dumps({"corpus":str(args.output.resolve()),
                      "sha256":digest,"examples":len(bundle["episodes"][0]["examples"]),
                      "source_digest":bundle["source_digest"],
                      "neural_weights_modified":False},sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
