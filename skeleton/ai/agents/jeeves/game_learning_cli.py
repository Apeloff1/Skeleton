"""Explicit local operator for the same Jeeves game-policy learning owners.

Files are private checkpoint/export artifacts, not application authority or
production promotion receipts. No web service or provider credentials are used.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any

MAX_POLICY_BYTES = 32 * 1024 * 1024
CHECKPOINT_SCHEMA = "skeleton.game.local_parallel_checkpoint.v1"


def _read(path: Path, maximum: int) -> bytes:
    if type(maximum) is not int or maximum < 1:
        raise ValueError("Input byte bound must be positive")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            raise ValueError("Input must be a bounded regular file")
        chunks, size = [], 0
        while size <= maximum:
            chunk = stream.read(min(65536, maximum + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
        if size > maximum:
            raise ValueError("Input changed beyond its byte limit")
        after = os.fstat(stream.fileno())
        final = os.stat(path, follow_symlinks=False)
        identity = lambda value: (
            value.st_dev,
            value.st_ino,
            value.st_size,
            value.st_mtime_ns,
            value.st_ctime_ns,
        )
        if (
            not stat.S_ISREG(final.st_mode)
            or identity(before) != identity(after)
            or identity(after) != identity(final)
        ):
            raise ValueError("Input identity changed while it was read")
        return b"".join(chunks)


def _json_read(path: Path) -> dict[str, Any]:
    value = json.loads(_read(path, MAX_POLICY_BYTES))
    if not isinstance(value, dict):
        raise TypeError("Checkpoint/project must be a JSON object")
    return value


def _write(path: Path, payload: bytes, *, replace: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or path.exists() and not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("Output must be a regular file and cannot be a symbolic link")
    if path.exists() and not replace:
        raise FileExistsError(
            "Output exists; use an explicit resume/fork or replacement option"
        )
    descriptor, temporary = tempfile.mkstemp(prefix=".game-learning-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _write_json(path: Path, value: Any, *, replace: bool) -> None:
    payload = (
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode()
    if len(payload) > MAX_POLICY_BYTES:
        raise ValueError("Checkpoint output exceeds its byte budget")
    _write(path, payload, replace=replace)


def _factory(args):
    from .game_learning_parallel import GameEnvironmentRequest

    rom = None
    tree = None
    lineage = {
        "operator": "explicit_local_cli",
        "target": args.target,
        "source_authority": "explicit local operator source choice; no application rights receipt",
    }
    if args.rom:
        from .game_rom_runtime import MAX_ROM_BYTES

        rom = _read(args.rom, MAX_ROM_BYTES)
        lineage["rom_digest"] = hashlib.sha256(rom).hexdigest()
    if args.project:
        project = _json_read(args.project)
        raw = project.get("files", project.get("tree", project))
        if isinstance(raw, list):
            raw = {item["path"]: item["content"] for item in raw}
        if not isinstance(raw, dict):
            raise ValueError("Project input must contain a bounded file mapping")
        tree = raw
        lineage["project_digest"] = hashlib.sha256(
            json.dumps(tree, sort_keys=True).encode()
        ).hexdigest()
    if rom is not None and tree is not None:
        raise ValueError("Select one explicit ROM or project execution source")
    dialect = None
    if tree is not None and "engine/manifest.json" in tree:
        manifest = json.loads(tree["engine/manifest.json"])
        if not isinstance(manifest, dict):
            raise ValueError("Project engine manifest must be an object")
        dialect = manifest.get("gameplay_dialect")
    native = args.core is not None or args.target.startswith("emulator:")
    core_id, registry_digest = None, None
    if native:
        from .game_emulator_catalog import GameEmulatorRegistry

        if rom is None or tree is not None:
            raise ValueError(
                "Installed-core local play requires --rom; large/multifile media use the streamed studio loader"
            )
        registry = GameEmulatorRegistry.from_environment()
        approved = registry.resolve(args.target)
        if args.core is not None and approved.core_id != args.core:
            approved = registry.resolve_core(args.core)
            if args.target.removeprefix("emulator:") not in approved.target_ids:
                raise ValueError(
                    "Requested installed core is not approved for this console"
                )
        core_id, registry_digest = approved.core_id, registry.registry_digest
        lineage.update(core_id=core_id, registry_digest=registry_digest)
    request = GameEnvironmentRequest(
        target_id=args.target,
        max_steps=args.episode_steps,
        tree=tree,
        rom_source=rom,
        cycles_per_step=args.cycles_per_step,
        kind="libretro" if native else "builtin",
        core_id=core_id,
        registry_digest=registry_digest,
        filename=args.rom.name if args.rom else "game.bin",
        frames_per_step=args.frames_per_step,
        gameplay_dialect=dialect,
    )
    factory = request.build
    # Return the serializable request alongside its ordinary environment factory.
    return factory, lineage, request


def _checkpoint(value):
    if value.get("schema_version") != CHECKPOINT_SCHEMA:
        return value, None
    if set(value) != {"schema_version", "policy", "parallel_state"} or not isinstance(
        value["policy"], dict
    ):
        raise ValueError("Local parallel checkpoint envelope is invalid")
    return value["policy"], value["parallel_state"]


def _train(args) -> dict[str, Any]:
    from .game_learning import GameLearningConfig, GamePolicyLearner
    from .game_learning_demonstrations import close_environment

    factory, lineage, environment_request = _factory(args)
    probe = factory()
    try:
        spec = probe.spec
    finally:
        close_environment(probe)
    if args.resume and args.fork_parent:
        raise ValueError("Choose exact resume or an explicit parent-policy fork")
    config = GameLearningConfig(
        seed=args.seed, max_updates=args.max_updates, max_episodes=256
    )
    pending_batch = None
    if args.resume:
        snapshot, pending_batch = _checkpoint(_json_read(args.policy_file))
        learner = GamePolicyLearner.from_snapshot(
            snapshot,
            expected_spec=spec,
            expected_config=config,
            expected_source_lineage=lineage,
        )
        if learner.policy_id != args.policy_id:
            raise ValueError(
                "Resume must retain the original configured policy identity"
            )
    elif args.fork_parent:
        learner = GamePolicyLearner.fork(
            _checkpoint(_json_read(args.fork_parent))[0],
            newpolicy_id=args.policy_id,
            newsource_lineage=lineage,
            config=config,
            expected_spec=spec,
        )
    else:
        if args.policy_file.exists():
            raise FileExistsError("Policy output exists; select resume or a new file")
        learner = GamePolicyLearner(
            spec, config, policy_id=args.policy_id, source_lineage=lineage
        )
    output_created = args.resume
    stop = False

    def cancelled():
        return stop

    parallel = (
        args.workers > 1
        or environment_request.kind == "libretro"
        or pending_batch is not None
    )

    def checkpoint(snapshot, trace, batch_state=None):
        nonlocal output_created
        if args.trace_directory and trace is not None:
            name = hashlib.sha256(trace["episode_id"].encode()).hexdigest() + ".json"
            destination = args.trace_directory / name
            if destination.exists():
                if _json_read(destination) != trace:
                    raise ValueError(
                        "Existing episode trace differs from the admitted episode"
                    )
            else:
                _write_json(destination, trace, replace=False)
        # The policy file is the commit point; no fallible audit write follows it.
        payload = (
            {
                "schema_version": CHECKPOINT_SCHEMA,
                "policy": snapshot,
                "parallel_state": batch_state,
            }
            if parallel
            else snapshot
        )
        _write_json(args.policy_file, payload, replace=output_created)
        output_created = True

    try:
        if parallel:
            from .game_learning_parallel import ParallelGamePolicyTrainer

            result = ParallelGamePolicyTrainer(
                learner, environment_request, actors=args.workers
            ).train(
                episodes=args.episodes,
                resume_state=pending_batch,
                on_checkpoint=checkpoint,
                cancel=cancelled,
            )
        else:
            result = learner.train(
                factory,
                episodes=args.episodes,
                on_checkpoint=checkpoint,
                cancel=cancelled,
            )
    except KeyboardInterrupt:
        stop = True
        return {
            "status": "interrupted",
            "message": "Only complete checkpointed episodes are preserved.",
            "policy_file": str(args.policy_file),
        }
    return {
        "status": "candidate_trained",
        "algorithm": "frozen_batch_local_actor_q_v1"
        if parallel
        else "tabular_q_learning_v1",
        "workers": args.workers if parallel else 1,
        "updates": result.updates,
        "committed_episodes": result.snapshot["committed_episodes"],
        "policy_digest": result.snapshot["snapshot_digest"],
        "policy_file": str(args.policy_file),
        "production_promotion": False,
    }


def _evaluate(args) -> dict[str, Any]:
    from .game_learning import GamePolicyLearner
    from .game_learning_demonstrations import close_environment

    factory, _, _ = _factory(args)
    probe = factory()
    try:
        spec = probe.spec
    finally:
        close_environment(probe)
    learner = GamePolicyLearner.from_snapshot(
        _checkpoint(_json_read(args.policy_file))[0], expected_spec=spec
    )
    baseline = (
        None if args.baseline is None else _checkpoint(_json_read(args.baseline))[0]
    )
    result = learner.evaluate(
        factory, heldout_seeds=args.heldout_seed, baseline_snapshot=baseline
    ).as_dict()
    _write_json(args.evidence_file, result, replace=args.force)
    return {
        "status": "candidate_measured",
        "evaluation_digest": result["evaluation_digest"],
        "evidence_file": str(args.evidence_file),
        "production_promotion": False,
    }


def _probe_goals(args) -> dict[str, Any]:
    from .game_emulator_goal_lab import (
        GoalExperimentConfig, MemoryGoal, evaluate_operator_native_goals,
    )

    if not args.rights_acknowledged or args.rom is None or args.project is not None:
        raise ValueError("Actual native ROM and operator source rights are required")
    if not args.target.startswith("emulator:"):
        raise ValueError("Native memory-goal probes require an approved libretro core")
    if args.evidence_file.exists():
        raise FileExistsError("Memory-goal experiment output already exists")
    if args.goal_file.resolve(strict=False) == args.evidence_file.resolve(strict=False):
        raise ValueError("Goal definition and output destinations must be separate")
    definition = _json_read(args.goal_file)
    if set(definition) != {"source_authority", "goals", "interventions"}:
        raise ValueError("Operator objective schema must include only source_authority/goals/interventions")
    goals_raw = definition["goals"]
    if not isinstance(goals_raw, list) or not 1 <= len(goals_raw) <= 8:
        raise ValueError("The input must declare one to eight explicit bounded memory goals")
    goals = tuple(MemoryGoal(**item) for item in goals_raw)
    _, _, request = _factory(args)
    result = evaluate_operator_native_goals(
        request,
        goals=goals,
        interventions=definition["interventions"],
        source_authority=definition["source_authority"],
        rights_acknowledged=True,
        config=GoalExperimentConfig(
            seed=args.seed, anchors=args.anchors, repeats=args.repeats,
            horizon=args.horizon, max_actual_steps=args.max_actual_steps,
        ),
    )
    _write_json(args.evidence_file, result, replace=False)
    return {
        "status": "operator_goals_physically_measured",
        "report_digest": result["report_digest"],
        "observed_active_only_goal_contrasts": result["measured_active_only_goal_contrasts"],
        "native_source_steps": result["actual_source_steps"],
        "evidence_file": str(args.evidence_file),
        "semantic_game_success_certified": False,
        "production_weight_updates": 0,
    }


def _plan_emulator(args) -> dict[str, Any]:
    from .game_emulator_planning_lab import (
        EmulatorPlanningConfig,
        run_native_confirmed_planning,
    )

    if not args.rights_acknowledged or args.rom is None or args.project is not None:
        raise ValueError("Physical planning requires one explicit rights-cleared ROM source")
    if args.evidence_file.exists():
        raise FileExistsError("Native planning evidence must be a new private file")
    destinations = {
        args.model_file.resolve(strict=False),
        args.training_report_file.resolve(strict=False),
        args.evidence_file.resolve(strict=False),
    }
    if len(destinations) != 3:
        raise ValueError("Training input and physical planning output locations must differ")
    _, _, request = _factory(args)
    model = _json_read(args.model_file)
    report = _json_read(args.training_report_file)
    results = run_native_confirmed_planning(
        request,
        model=model, training_report=report,
        rights_acknowledged=True,
        config=EmulatorPlanningConfig(
            seed=args.seed, anchors=args.anchors, horizon=args.horizon,
            beam_width=args.beam_width, action_subset=args.action_subset,
            proposal_count=args.proposal_count, repeats=args.repeats,
            max_actual_steps=args.max_actual_steps, objective=args.objective,
        ),
    )
    _write_json(args.evidence_file, results, replace=False)
    return {
        "status": "measured_native_model_plans",
        "evidence_file": str(args.evidence_file),
        "report_digest": results["report_digest"],
        "real_emulator_steps": results["real_emulator_steps"],
        "physically_validated_plans": results["tested_plan_count"],
        "physically_positive_plans": results["actual_positive_plans"],
        "neural_or_q_weight_updates": 0,
        "production_promotion": False,
    }


def _fit_emulator_world_model(args) -> dict[str, Any]:
    from .game_emulator_neural_world import (
        NeuralWorldConfig,
        train_neural_world_from_evidence,
    )

    if args.model_file.exists() or args.training_report_file.exists():
        raise FileExistsError("Neural-world outputs must be new, not overwrite a previous checkpoint")
    paths = [
        args.policy_file.resolve(strict=False),
        args.evidence_file.resolve(strict=False),
        args.model_file.resolve(strict=False),
        args.training_report_file.resolve(strict=False),
    ]
    if len(set(paths)) != len(paths):
        raise ValueError("Neural training source and destination paths must be distinct")
    policy = _json_read(args.policy_file)
    evidence = _json_read(args.evidence_file)
    model, report = train_neural_world_from_evidence(
        evidence, policy,
        config=NeuralWorldConfig(
            seed=args.seed,
            width=args.width,
            epochs=args.epochs,
            minibatch=args.minibatch,
            learning_rate=args.learning_rate,
            weight_decay=args.weight_decay,
            clip_gradient=args.clip_gradient,
            max_samples=args.max_samples,
            min_relative_holdout_gain=args.min_relative_holdout_gain,
        ),
    )
    _write_json(args.model_file, model, replace=False)
    _write_json(args.training_report_file, report, replace=False)
    return {
        "status": report["candidate_status"],
        "candidate_model_file": str(args.model_file),
        "training_report_file": str(args.training_report_file),
        "candidate_model_sha256": model["model_digest"],
        "actual_neural_optimizer_steps": model["real_optimizer_steps"],
        "actual_gradient_evaluations": model["gradient_evaluations"],
        "heldout_relative_improvement": report["relative_reduction_vs_mean_baseline"],
        "jeeves_production_weight_updates": 0,
        "production_model_promotion": False,
    }


def _cross_core_comparison(args) -> dict[str, Any]:
    from .game_emulator_cross_core_lab import CrossCoreConfig, compare_real_emulator_cores

    if not args.rights_acknowledged:
        raise ValueError("Exact rights-cleared ROM input acknowledgment is required")
    if args.project is not None or args.rom is None or not args.target.startswith("emulator:"):
        raise ValueError("Only installed, approved libretro cores sharing one ROM are comparable")
    if args.evidence_file.exists():
        raise FileExistsError("Cross-core comparison output already exists")
    cores = tuple(args.core)
    if len(cores) != len(set(cores)):
        raise ValueError("Comparison requires distinct core IDs")
    from argparse import Namespace

    requests = []
    for core in cores:
        options = vars(args).copy()
        options["core"] = core
        _, _, request = _factory(Namespace(**options))
        if request.kind != "libretro":
            raise ValueError("Expected actual approved native libretro runtime")
        requests.append(request)
    report = compare_real_emulator_cores(
        requests,
        rights_acknowledged=True,
        config=CrossCoreConfig(
            seed=args.seed, steps=args.comparison_steps,
            repetitions=args.repetitions, max_native_steps=args.max_native_steps,
        ),
    )
    _write_json(args.evidence_file, report, replace=False)
    return {
        "status": "measured_native_core_comparison",
        "report_digest": report["report_digest"],
        "compared_cores": report["compared_approved_native_cores"],
        "actual_native_steps": report["actual_native_steps"],
        "all_repetitions_reproducible": report["all_repeats_stable"],
        "evidence_file": str(args.evidence_file),
        "production_neural_weight_updates": 0,
        "hardware_certification": False,
    }


def _emulator_experiment(args) -> dict[str, Any]:
    from .game_emulator_experiment_lab import (
        EmulatorExperimentConfig,
        MemoryWatch,
        run_emulator_experiment_matrix,
    )

    if not args.rights_acknowledged:
        raise ValueError("Rights-cleared source acknowledgement is required")
    if args.project is not None or args.rom is None:
        raise ValueError("Experimental emulator measurement requires a local owned ROM")
    if args.evidence_file.exists():
        raise FileExistsError("Experiment evidence destination already exists")
    _, lineage, request = _factory(args)
    watches = ()
    if args.memory_watch_file is not None:
        root = _json_read(args.memory_watch_file)
        rows = root.get("watches")
        if not isinstance(rows, list) or len(rows) > 8:
            raise ValueError("Expected at most eight explicit memory watches")
        watches = tuple(MemoryWatch(**value) for value in rows)
    report = run_emulator_experiment_matrix(
        request,
        rights_acknowledged=True,
        config=EmulatorExperimentConfig(
            seed=args.seed,
            anchors=args.anchors,
            repeats=args.repeats,
            longest_duration=args.longest_duration,
            max_conditions=args.max_conditions,
            max_native_steps=args.max_native_steps,
            include_multiplayer=args.include_multiplayer,
            include_keyboard=args.include_keyboard,
            include_memory_audit=args.memory_watch_file is not None,
        ),
        watches=watches,
    )
    _write_json(args.evidence_file, report, replace=False)
    return {
        "status": "native_controlled_experiments_recorded",
        "report_digest": report["report_digest"],
        "actual_experiment_steps": report["actual_native_steps_including_probe_anchors"],
        "repeated_trials_stable": report["all_trials_reproducible"],
        "evidence_file": str(args.evidence_file),
        "neural_weight_updates": 0,
        "production_promotion": False,
    }


def _deep_emulator(args) -> dict[str, Any]:
    from .game_emulator_training_lab import EmulatorLabConfig, run_emulator_training_lab

    if not args.rights_acknowledged:
        raise ValueError("Explicit source rights acknowledgement is required to train on ROM content")
    if args.project is not None or args.rom is None:
        raise ValueError("Deep emulator training requires a local rights-cleared ROM, not a reference project")
    if args.policy_file.exists() or args.evidence_file.exists() or args.checkpoint_file.exists():
        raise ValueError("Deep emulator outputs must be new files; use distinct destinations")
    targets = {
        args.policy_file.resolve(strict=False),
        args.evidence_file.resolve(strict=False),
        args.checkpoint_file.resolve(strict=False),
    }
    if len(targets) != 3:
        raise ValueError("Policy, evidence and checkpoint must use distinct destination files")
    _, lineage, request = _factory(args)
    lineage["rights_acknowledged"] = True
    config = EmulatorLabConfig(
        max_runs=args.max_runs, steps_per_run=args.episode_steps,
        stagnation_runs=args.stagnation_runs,
        checkpoint_stride=args.checkpoint_stride,
        counterfactual_actions=args.counterfactual_actions,
        boomerang_interval=args.boomerang_interval,
        boomerang_retained=args.boomerang_retained,
        heldout_episodes=args.heldout_episodes,
        seed=args.seed,
    )

    def checkpoint(snapshot, progress):
        # The operator selected the destination before starting. This is a
        # private crash-recovery record; it is NOT a production model promotion.
        _write_json(
            args.checkpoint_file,
            {"schema_version": "skeleton.game.emulator_lab_checkpoint.v1",
             "policy_snapshot": snapshot, "progress": progress,
             "production_promotion_authorized": False},
            replace=True,
        )

    result = run_emulator_training_lab(
        request, source_lineage=lineage, config=config,
        policy_id=args.policy_id, on_checkpoint=checkpoint,
    )
    _write_json(args.policy_file, result["policy_snapshot"], replace=False)
    evidence = {key: value for key, value in result.items() if key != "policy_snapshot"}
    evidence["policy_snapshot_digest"] = result["policy_snapshot"]["snapshot_digest"]
    evidence["evidence_digest"] = hashlib.sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    ).hexdigest()
    _write_json(args.evidence_file, evidence, replace=False)
    return {
        "status": result["status"],
        "policy_file": str(args.policy_file),
        "evidence_file": str(args.evidence_file),
        "checkpoint_file": str(args.checkpoint_file),
        "report_digest": result["report_digest"],
        "real_q_updates": result["actual_q_table_updates"],
        "real_neural_weight_updates": 0,
        "runs": result["run_count"],
        "hardware_compatibility_verified": False,
    }


def _native(args) -> dict[str, Any]:
    from .game_rom_generation import build_original_dmg_game

    result = build_original_dmg_game(seed=args.seed, title=args.title)
    rom = base64.b64decode(result["rom_base64"], validate=True)
    _write(args.output, rom, replace=args.force)
    _write_json(
        args.output.with_suffix(args.output.suffix + ".json"),
        result["manifest"],
        replace=args.force,
    )
    return {
        "status": "original_rom_built",
        "rom_digest": result["rom_digest"],
        "rom_bytes": result["rom_bytes"],
        "output": str(args.output),
        "hardware_compatibility_verified": False,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "catalog", help="Print actual target/source/execution readiness"
    )
    native = commands.add_parser(
        "build-dmg", help="Build an original seeded maze cartridge"
    )
    native.add_argument("--seed", type=int, default=0)
    native.add_argument("--title", default="Signal Garden")
    native.add_argument("--output", type=Path, required=True)
    native.add_argument("--force", action="store_true")






    goal = commands.add_parser(
        "probe-emulator-goals",
        help="Measure operator-defined native memory objectives vs same-timeline neutral controls",
    )
    goal.add_argument("--target", required=True)
    goal.add_argument("--rom", type=Path, required=True)
    goal.add_argument("--project", type=Path)
    goal.add_argument("--core", required=True)
    goal.add_argument("--episode-steps", type=int, default=32)
    goal.add_argument("--frames-per-step", type=int, default=1)
    goal.add_argument("--cycles-per-step", type=int, default=1824)
    goal.add_argument("--goal-file", type=Path, required=True)
    goal.add_argument("--evidence-file", type=Path, required=True)
    goal.add_argument("--seed", type=int, default=0)
    goal.add_argument("--anchors", type=int, default=2)
    goal.add_argument("--repeats", type=int, default=2)
    goal.add_argument("--horizon", type=int, default=6)
    goal.add_argument("--max-actual-steps", type=int, default=2048)
    goal.add_argument("--rights-acknowledged", action="store_true")
    plan = commands.add_parser(
        "plan-emulator",
        help="Physically compare candidate neural action plans vs identical-state neutral baselines",
    )
    plan.add_argument("--target", required=True)
    plan.add_argument("--rom", type=Path, required=True)
    plan.add_argument("--project", type=Path)
    plan.add_argument("--core")
    plan.add_argument("--episode-steps", type=int, default=32)
    plan.add_argument("--frames-per-step", type=int, default=1)
    plan.add_argument("--cycles-per-step", type=int, default=1824)
    plan.add_argument("--model-file", type=Path, required=True)
    plan.add_argument("--training-report-file", type=Path, required=True)
    plan.add_argument("--evidence-file", type=Path, required=True)
    plan.add_argument("--seed", type=int, default=0)
    plan.add_argument("--anchors", type=int, default=2)
    plan.add_argument("--horizon", type=int, default=4)
    plan.add_argument("--beam-width", type=int, default=8)
    plan.add_argument("--action-subset", type=int, default=8)
    plan.add_argument("--proposal-count", type=int, default=3)
    plan.add_argument("--repeats", type=int, default=2)
    plan.add_argument("--max-actual-steps", type=int, default=512)
    plan.add_argument(
        "--objective",
        choices=["measured_reward", "visual_activity", "audio_activity", "low_visual_activity"],
        default="measured_reward",
    )
    plan.add_argument("--rights-acknowledged", action="store_true")
    world = commands.add_parser(
        "fit-emulator-world-model",
        help="Perform REAL bounded neural optimizer steps on verified ROM traces; never promote Jeeves weights",
    )
    world.add_argument("--policy-file", type=Path, required=True)
    world.add_argument("--evidence-file", type=Path, required=True)
    world.add_argument("--model-file", type=Path, required=True)
    world.add_argument("--training-report-file", type=Path, required=True)
    world.add_argument("--seed", type=int, default=0)
    world.add_argument("--width", type=int, default=20)
    world.add_argument("--epochs", type=int, default=8)
    world.add_argument("--minibatch", type=int, default=16)
    world.add_argument("--learning-rate", type=float, default=0.003)
    world.add_argument("--weight-decay", type=float, default=0.0001)
    world.add_argument("--clip-gradient", type=float, default=3.0)
    world.add_argument("--max-samples", type=int, default=2048)
    world.add_argument("--min-relative-holdout-gain", type=float, default=0.01)
    cross = commands.add_parser(
        "compare-emulator-cores",
        help="Execute the same owned ROM and exact controls on 2-4 approved libretro cores",
    )
    cross.add_argument("--target", required=True)
    cross.add_argument("--rom", required=True, type=Path)
    cross.add_argument("--project", type=Path)
    cross.add_argument("--core", action="append", required=True)
    cross.add_argument("--episode-steps", type=int, default=32)
    cross.add_argument("--comparison-steps", type=int, default=16)
    cross.add_argument("--repetitions", type=int, default=2)
    cross.add_argument("--max-native-steps", type=int, default=256)
    cross.add_argument("--seed", type=int, default=0)
    cross.add_argument("--frames-per-step", type=int, default=1)
    cross.add_argument("--cycles-per-step", type=int, default=1824)
    cross.add_argument("--rights-acknowledged", action="store_true")
    cross.add_argument("--evidence-file", required=True, type=Path)
    experiment = commands.add_parser(
        "experiment-emulator",
        help="Run actual checkpointed ROM counterfactuals; never update model weights",
    )
    experiment.add_argument("--target", required=True)
    experiment.add_argument("--rom", type=Path, required=True)
    experiment.add_argument("--project", type=Path)
    experiment.add_argument("--core")
    experiment.add_argument("--frames-per-step", type=int, default=1)
    experiment.add_argument("--cycles-per-step", type=int, default=1824)
    experiment.add_argument("--episode-steps", type=int, default=32)
    experiment.add_argument("--anchors", type=int, default=3)
    experiment.add_argument("--repeats", type=int, default=2)
    experiment.add_argument("--longest-duration", type=int, default=4)
    experiment.add_argument("--max-conditions", type=int, default=32)
    experiment.add_argument("--max-native-steps", type=int, default=1536)
    experiment.add_argument("--seed", type=int, default=0)
    experiment.add_argument("--include-multiplayer", action=argparse.BooleanOptionalAction, default=True)
    experiment.add_argument("--include-keyboard", action=argparse.BooleanOptionalAction, default=True)
    experiment.add_argument("--memory-watch-file", type=Path)
    experiment.add_argument("--rights-acknowledged", action="store_true")
    experiment.add_argument("--evidence-file", type=Path, required=True)
    deep = commands.add_parser(
        "train-emulator-deep",
        help="Actual native/DMG ROM Q training with reverse replay and ten-run saturation audits",
    )
    deep.add_argument("--target", required=True)
    deep.add_argument("--rom", required=True, type=Path)
    deep.add_argument("--core")
    deep.add_argument("--project", type=Path)
    deep.add_argument("--frames-per-step", type=int, default=1)
    deep.add_argument("--cycles-per-step", type=int, default=1824)
    deep.add_argument("--episode-steps", type=int, default=24)
    deep.add_argument("--max-runs", type=int, default=48)
    deep.add_argument("--stagnation-runs", type=int, default=10)
    deep.add_argument("--checkpoint-stride", type=int, default=6)
    deep.add_argument("--counterfactual-actions", type=int, default=3)
    deep.add_argument("--boomerang-interval", type=int, default=5)
    deep.add_argument("--boomerang-retained", type=int, default=4)
    deep.add_argument("--heldout-episodes", type=int, default=2)
    deep.add_argument("--seed", type=int, default=0)
    deep.add_argument("--policy-id", default="emulator-deep-local-candidate")
    deep.add_argument("--policy-file", type=Path, required=True)
    deep.add_argument("--evidence-file", type=Path, required=True)
    deep.add_argument("--checkpoint-file", type=Path, required=True)
    deep.add_argument("--rights-acknowledged", action="store_true")
    for name in ("train", "evaluate"):
        command = commands.add_parser(name)
        command.add_argument("--target", required=True)
        command.add_argument("--rom", type=Path)
        command.add_argument("--project", type=Path)
        command.add_argument("--episode-steps", type=int, default=256)
        command.add_argument("--cycles-per-step", type=int, default=1824)
        command.add_argument(
            "--core", help="Explicit approved installed libretro core identity"
        )
        command.add_argument("--frames-per-step", type=int, default=1)
        command.add_argument("--policy-file", type=Path, required=True)
        if name == "train":
            command.add_argument("--episodes", type=int, default=16)
            command.add_argument("--seed", type=int, default=0)
            command.add_argument("--max-updates", type=int, default=65536)
            command.add_argument("--policy-id", default="local-game-policy")
            command.add_argument("--resume", action="store_true")
            command.add_argument("--fork-parent", type=Path)
            command.add_argument("--trace-directory", type=Path)
            command.add_argument("--workers", type=int, default=1, choices=range(1, 9))
        else:
            command.add_argument(
                "--heldout-seed", type=int, action="append", required=True
            )
            command.add_argument("--baseline", type=Path)
            command.add_argument("--evidence-file", type=Path, required=True)
            command.add_argument("--force", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "catalog":
            from .game_console_catalog import execution_inventory

            result = execution_inventory()
        elif args.command == "train":
            result = _train(args)
        elif args.command == "evaluate":
            result = _evaluate(args)
        elif args.command == "train-emulator-deep":
            result = _deep_emulator(args)
        elif args.command == "experiment-emulator":
            result = _emulator_experiment(args)
        elif args.command == "compare-emulator-cores":
            result = _cross_core_comparison(args)
        elif args.command == "fit-emulator-world-model":
            result = _fit_emulator_world_model(args)
        elif args.command == "plan-emulator":
            result = _plan_emulator(args)
        elif args.command == "probe-emulator-goals":
            result = _probe_goals(args)
        else:
            result = _native(args)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (ValueError, TypeError, OSError, KeyError) as exc:
        print(
            json.dumps({"status": "rejected", "message": str(exc)[:1000]}),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
