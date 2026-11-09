"""Deterministic historical scripting VMs for Jeeves game-engine sandboxes.

The scripting plane is deliberately data-only. It accepts typed instruction
recipes, compiles canonical bytecode documents, and executes them in a
gas-bounded interpreter. It never evals, imports, executes Python source, or
permits host callbacks.

The capability envelope grows with the engine era: tiny rule programs in the
Pong/arcade generations, fixed-point state bytecode in 8/16-bit engines,
event/call capable object scripts through 3D/HD, deterministic job-friendly
state programs in modern engines, and a schema-bound hybrid behavior VM for
the next era.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping, Sequence

from .game_engine_lab import (
    EngineEra,
    GameEngineLabError,
    NumericMode,
    SandboxPatch,
    engine_era_profile,
)
from .game_engine_runtime import RoutedEngineSandbox

MAX_SCRIPT_ID = 64
MAX_EVENT_NAME = 64


class ScriptOp(str, Enum):
    NOP = "nop"
    CONST = "const"
    MOV = "mov"
    ADD = "add"
    SUB = "sub"
    MUL = "mul"
    DIV = "div"
    MIN = "min"
    MAX = "max"
    CLAMP = "clamp"
    CMP_EQ = "cmp_eq"
    CMP_LT = "cmp_lt"
    CMP_GT = "cmp_gt"
    JUMP = "jump"
    JUMP_IF = "jump_if"
    LOAD_STATE = "load_state"
    STORE_STATE = "store_state"
    EMIT = "emit"
    CALL = "call"
    RET = "ret"
    HALT = "halt"


@dataclass(frozen=True, slots=True)
class EraScriptPolicy:
    era: EngineEra
    dialect: str
    allowed: tuple[ScriptOp, ...]
    max_scripts: int
    max_instructions: int
    max_steps: int
    registers: int
    state_slots: int
    call_depth: int
    max_events: int
    numeric_mode: NumericMode

    def __post_init__(self) -> None:
        for value in (
            self.max_scripts,
            self.max_instructions,
            self.max_steps,
            self.registers,
            self.state_slots,
            self.max_events,
        ):
            if value < 1:
                raise GameEngineLabError(
                    "script policy positive bounds required"
                )
        if self.call_depth < 0:
            raise GameEngineLabError(
                "script call depth cannot be negative"
            )


_BASE = (
    ScriptOp.NOP,
    ScriptOp.CONST,
    ScriptOp.MOV,
    ScriptOp.ADD,
    ScriptOp.SUB,
    ScriptOp.LOAD_STATE,
    ScriptOp.STORE_STATE,
    ScriptOp.EMIT,
    ScriptOp.HALT,
)
_BRANCH = _BASE + (
    ScriptOp.CMP_EQ,
    ScriptOp.CMP_LT,
    ScriptOp.JUMP,
    ScriptOp.JUMP_IF,
)
_ARITH = _BRANCH + (
    ScriptOp.MUL,
    ScriptOp.DIV,
    ScriptOp.MIN,
    ScriptOp.MAX,
    ScriptOp.CLAMP,
    ScriptOp.CMP_GT,
)
_CALL = _ARITH + (
    ScriptOp.CALL,
    ScriptOp.RET,
)


ERA_SCRIPT_POLICIES: Mapping[EngineEra, EraScriptPolicy] = {
    EngineEra.PONG: EraScriptPolicy(
        EngineEra.PONG,
        "hardwired_rule_table",
        _BASE,
        2,
        16,
        32,
        4,
        4,
        0,
        4,
        NumericMode.INTEGER,
    ),
    EngineEra.ARCADE: EraScriptPolicy(
        EngineEra.ARCADE,
        "arcade_state_bytecode",
        _BRANCH,
        8,
        32,
        96,
        8,
        8,
        0,
        8,
        NumericMode.FIXED8,
    ),
    EngineEra.EIGHT_BIT: EraScriptPolicy(
        EngineEra.EIGHT_BIT,
        "8bit_fixed_bytecode",
        _BRANCH,
        16,
        64,
        192,
        8,
        16,
        0,
        12,
        NumericMode.FIXED8,
    ),
    EngineEra.SIXTEEN_BIT: EraScriptPolicy(
        EngineEra.SIXTEEN_BIT,
        "16bit_object_bytecode",
        _ARITH,
        32,
        128,
        512,
        16,
        32,
        0,
        24,
        NumericMode.FIXED16,
    ),
    EngineEra.EARLY_3D: EraScriptPolicy(
        EngineEra.EARLY_3D,
        "event_object_bytecode",
        _CALL,
        64,
        192,
        768,
        24,
        64,
        8,
        32,
        NumericMode.FIXED16,
    ),
    EngineEra.FIXED_3D: EraScriptPolicy(
        EngineEra.FIXED_3D,
        "scene_object_vm",
        _CALL,
        128,
        256,
        1_024,
        32,
        96,
        16,
        48,
        NumericMode.FLOAT32,
    ),
    EngineEra.SHADER: EraScriptPolicy(
        EngineEra.SHADER,
        "console_gameplay_vm",
        _CALL,
        192,
        384,
        1_536,
        48,
        128,
        24,
        64,
        NumericMode.FLOAT32,
    ),
    EngineEra.HD: EraScriptPolicy(
        EngineEra.HD,
        "hd_event_vm",
        _CALL,
        256,
        512,
        2_048,
        64,
        192,
        32,
        96,
        NumericMode.FLOAT32,
    ),
    EngineEra.OPEN_WORLD: EraScriptPolicy(
        EngineEra.OPEN_WORLD,
        "streamed_world_vm",
        _CALL,
        384,
        768,
        3_072,
        96,
        256,
        48,
        128,
        NumericMode.FLOAT32,
    ),
    EngineEra.MODERN: EraScriptPolicy(
        EngineEra.MODERN,
        "deterministic_ecs_behavior_vm",
        _CALL,
        512,
        1_024,
        4_096,
        128,
        384,
        64,
        192,
        NumericMode.FLOAT32,
    ),
    EngineEra.NEXT: EraScriptPolicy(
        EngineEra.NEXT,
        "schema_bound_hybrid_behavior_vm",
        _CALL,
        768,
        1_536,
        6_144,
        192,
        512,
        96,
        256,
        NumericMode.FLOAT64,
    ),
}


def script_policy(
    era: EngineEra | str,
) -> EraScriptPolicy:
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
    return ERA_SCRIPT_POLICIES[key]


Operand = int | float | str


@dataclass(frozen=True, slots=True)
class ScriptInstruction:
    op: ScriptOp
    args: tuple[Operand, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.op, ScriptOp):
            object.__setattr__(
                self,
                "op",
                ScriptOp(str(self.op)),
            )
        for value in self.args:
            if isinstance(value, bool) or not isinstance(
                value,
                (int, float, str),
            ):
                raise GameEngineLabError(
                    "script operands must be bounded primitive values"
                )
            if isinstance(value, float) and not math.isfinite(value):
                raise GameEngineLabError(
                    "script operands must be finite"
                )
            if isinstance(value, str) and len(value) > MAX_EVENT_NAME:
                raise GameEngineLabError(
                    "script string operand exceeds limit"
                )


@dataclass(frozen=True, slots=True)
class ScriptSource:
    script_id: str
    instructions: tuple[ScriptInstruction, ...]

    def __post_init__(self) -> None:
        if (
            not self.script_id
            or len(self.script_id) > MAX_SCRIPT_ID
            or not all(
                char.isalnum()
                or char in "_.-"
                for char in self.script_id
            )
        ):
            raise GameEngineLabError(
                "script id must be bounded and path-safe"
            )
        if not self.instructions:
            raise GameEngineLabError(
                "script requires at least one instruction"
            )


@dataclass(frozen=True, slots=True)
class CompiledScript:
    script_id: str
    era: EngineEra
    dialect: str
    bytecode: tuple[
        tuple[str, tuple[Operand, ...]],
        ...,
    ]
    source_digest: str
    digest: str

    def document(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "script_id": self.script_id,
            "engine_era": self.era.value,
            "dialect": self.dialect,
            "bytecode": [
                [op, list(args)]
                for op, args
                in self.bytecode
            ],
            "source_digest": self.source_digest,
            "digest": self.digest,
            "executable_host_code": False,
        }


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
        _canonical(value).encode("utf-8")
    ).hexdigest()


def _source_document(
    source: ScriptSource,
) -> dict[str, object]:
    return {
        "script_id": source.script_id,
        "instructions": [
            [
                instruction.op.value,
                list(instruction.args),
            ]
            for instruction
            in source.instructions
        ],
    }


def _register(
    value: Operand,
    policy: EraScriptPolicy,
) -> int:
    if isinstance(value, bool) or type(value) is not int:
        raise GameEngineLabError(
            "register operand must be integer"
        )
    if not 0 <= value < policy.registers:
        raise GameEngineLabError(
            "register operand outside era limit"
        )
    return value


def _state_slot(
    value: Operand,
    policy: EraScriptPolicy,
) -> int:
    if isinstance(value, bool) or type(value) is not int:
        raise GameEngineLabError(
            "state slot operand must be integer"
        )
    if not 0 <= value < policy.state_slots:
        raise GameEngineLabError(
            "state slot outside era limit"
        )
    return value


def _target(
    value: Operand,
    length: int,
) -> int:
    if isinstance(value, bool) or type(value) is not int:
        raise GameEngineLabError(
            "control-flow target must be integer"
        )
    if not 0 <= value < length:
        raise GameEngineLabError(
            "control-flow target outside program"
        )
    return value


def _number(
    value: Operand,
) -> float:
    if isinstance(value, bool) or not isinstance(
        value,
        (int, float),
    ):
        raise GameEngineLabError(
            "numeric operand required"
        )
    result = float(value)
    if not math.isfinite(result):
        raise GameEngineLabError(
            "numeric operand must be finite"
        )
    return result


def _validate_instruction(
    instruction: ScriptInstruction,
    policy: EraScriptPolicy,
    length: int,
) -> None:
    op = instruction.op
    args = instruction.args
    if op not in policy.allowed:
        raise GameEngineLabError(
            f"{op.value} opcode unavailable in {policy.era.value}"
        )

    if op in {
        ScriptOp.NOP,
        ScriptOp.RET,
        ScriptOp.HALT,
    }:
        expected = 0
    elif op is ScriptOp.CONST:
        expected = 2
    elif op in {
        ScriptOp.MOV,
        ScriptOp.LOAD_STATE,
        ScriptOp.STORE_STATE,
    }:
        expected = 2
    elif op in {
        ScriptOp.ADD,
        ScriptOp.SUB,
        ScriptOp.MUL,
        ScriptOp.DIV,
        ScriptOp.MIN,
        ScriptOp.MAX,
        ScriptOp.CMP_EQ,
        ScriptOp.CMP_LT,
        ScriptOp.CMP_GT,
    }:
        expected = 3
    elif op is ScriptOp.CLAMP:
        expected = 4
    elif op in {
        ScriptOp.JUMP,
        ScriptOp.CALL,
    }:
        expected = 1
    elif op is ScriptOp.JUMP_IF:
        expected = 2
    elif op is ScriptOp.EMIT:
        expected = 2
    else:
        raise GameEngineLabError(
            f"unhandled script opcode: {op.value}"
        )
    if len(args) != expected:
        raise GameEngineLabError(
            f"{op.value} expects {expected} operands"
        )

    if op is ScriptOp.CONST:
        _register(args[0], policy)
        _number(args[1])
    elif op is ScriptOp.MOV:
        _register(args[0], policy)
        _register(args[1], policy)
    elif op in {
        ScriptOp.ADD,
        ScriptOp.SUB,
        ScriptOp.MUL,
        ScriptOp.DIV,
        ScriptOp.MIN,
        ScriptOp.MAX,
        ScriptOp.CMP_EQ,
        ScriptOp.CMP_LT,
        ScriptOp.CMP_GT,
    }:
        _register(args[0], policy)
        _register(args[1], policy)
        _register(args[2], policy)
    elif op is ScriptOp.CLAMP:
        _register(args[0], policy)
        _register(args[1], policy)
        _register(args[2], policy)
        _register(args[3], policy)
    elif op is ScriptOp.LOAD_STATE:
        _register(args[0], policy)
        _state_slot(args[1], policy)
    elif op is ScriptOp.STORE_STATE:
        _state_slot(args[0], policy)
        _register(args[1], policy)
    elif op in {
        ScriptOp.JUMP,
        ScriptOp.CALL,
    }:
        _target(args[0], length)
    elif op is ScriptOp.JUMP_IF:
        _register(args[0], policy)
        _target(args[1], length)
    elif op is ScriptOp.EMIT:
        if (
            not isinstance(args[0], str)
            or not args[0]
        ):
            raise GameEngineLabError(
                "emit event name must be non-empty text"
            )
        _register(args[1], policy)


class EraScriptCompiler:
    """Validate and canonicalize bounded game behavior bytecode."""

    def compile(
        self,
        era: EngineEra | str,
        source: ScriptSource,
    ) -> CompiledScript:
        policy = script_policy(era)
        if (
            len(source.instructions)
            > policy.max_instructions
        ):
            raise GameEngineLabError(
                "script exceeds era instruction budget"
            )
        for instruction in source.instructions:
            _validate_instruction(
                instruction,
                policy,
                len(source.instructions),
            )
        if (
            source.instructions[-1].op
            is not ScriptOp.HALT
        ):
            raise GameEngineLabError(
                "script must end with halt"
            )
        source_doc = _source_document(
            source
        )
        source_digest = _digest(
            source_doc
        )
        bytecode = tuple(
            (
                instruction.op.value,
                instruction.args,
            )
            for instruction
            in source.instructions
        )
        identity = {
            "script_id": source.script_id,
            "engine_era": policy.era.value,
            "dialect": policy.dialect,
            "bytecode": bytecode,
            "source_digest": source_digest,
        }
        return CompiledScript(
            source.script_id,
            policy.era,
            policy.dialect,
            bytecode,
            source_digest,
            _digest(identity),
        )

    def compile_all(
        self,
        era: EngineEra | str,
        sources: Iterable[ScriptSource],
    ) -> tuple[CompiledScript, ...]:
        values = tuple(sources)
        policy = script_policy(era)
        if len(values) > policy.max_scripts:
            raise GameEngineLabError(
                "script count exceeds era budget"
            )
        ids = tuple(
            source.script_id
            for source in values
        )
        if len(ids) != len(set(ids)):
            raise GameEngineLabError(
                "script ids must be unique"
            )
        return tuple(
            sorted(
                (
                    self.compile(
                        era,
                        source,
                    )
                    for source in values
                ),
                key=lambda script:
                    script.script_id,
            )
        )


def _quantize(
    mode: NumericMode,
    value: float,
) -> float:
    if not math.isfinite(value):
        raise GameEngineLabError(
            "script arithmetic produced non-finite value"
        )
    if mode is NumericMode.INTEGER:
        return float(
            int(
                round(value)
            )
        )
    if mode is NumericMode.FIXED8:
        return round(
            value * 256
        ) / 256
    if mode is NumericMode.FIXED16:
        return round(
            value * 65_536
        ) / 65_536
    if mode is NumericMode.FLOAT32:
        return struct.unpack(
            "!f",
            struct.pack(
                "!f",
                float(value),
            ),
        )[0]
    return round(
        float(value),
        12,
    )


@dataclass(frozen=True, slots=True)
class ScriptEvent:
    name: str
    value: float


@dataclass(frozen=True, slots=True)
class ScriptExecution:
    script_id: str
    era: EngineEra
    halted: bool
    exhausted: bool
    steps: int
    registers: tuple[float, ...]
    state: tuple[float, ...]
    events: tuple[ScriptEvent, ...]
    digest: str


class ScriptVM:
    """No-host-callback deterministic interpreter with strict gas bounds."""

    def __init__(
        self,
        era: EngineEra | str,
    ) -> None:
        self.policy = script_policy(
            era
        )

    def run(
        self,
        script: CompiledScript,
        *,
        inputs: Sequence[float] = (),
        state: Sequence[float] = (),
    ) -> ScriptExecution:
        if script.era is not self.policy.era:
            raise GameEngineLabError(
                "script era does not match VM"
            )
        registers = [
            0.0
            for _ in range(
                self.policy.registers
            )
        ]
        for index, value in enumerate(
            inputs[
                : self.policy.registers
            ]
        ):
            registers[index] = _quantize(
                self.policy.numeric_mode,
                float(value),
            )
        memory = [
            0.0
            for _ in range(
                self.policy.state_slots
            )
        ]
        for index, value in enumerate(
            state[
                : self.policy.state_slots
            ]
        ):
            memory[index] = _quantize(
                self.policy.numeric_mode,
                float(value),
            )

        pc = 0
        steps = 0
        call_stack: list[int] = []
        events: list[ScriptEvent] = []
        halted = False
        exhausted = False
        code = script.bytecode

        while (
            0 <= pc < len(code)
            and not halted
        ):
            if steps >= self.policy.max_steps:
                exhausted = True
                break
            op = ScriptOp(
                code[pc][0]
            )
            args = code[pc][1]
            steps += 1
            next_pc = pc + 1

            if op is ScriptOp.NOP:
                pass
            elif op is ScriptOp.CONST:
                dest = int(args[0])
                registers[dest] = _quantize(
                    self.policy.numeric_mode,
                    _number(args[1]),
                )
            elif op is ScriptOp.MOV:
                registers[
                    int(args[0])
                ] = registers[
                    int(args[1])
                ]
            elif op in {
                ScriptOp.ADD,
                ScriptOp.SUB,
                ScriptOp.MUL,
                ScriptOp.DIV,
                ScriptOp.MIN,
                ScriptOp.MAX,
                ScriptOp.CMP_EQ,
                ScriptOp.CMP_LT,
                ScriptOp.CMP_GT,
            }:
                dest = int(args[0])
                left = registers[
                    int(args[1])
                ]
                right = registers[
                    int(args[2])
                ]
                if op is ScriptOp.ADD:
                    value = left + right
                elif op is ScriptOp.SUB:
                    value = left - right
                elif op is ScriptOp.MUL:
                    value = left * right
                elif op is ScriptOp.DIV:
                    value = (
                        0.0
                        if right == 0.0
                        else left / right
                    )
                elif op is ScriptOp.MIN:
                    value = min(
                        left,
                        right,
                    )
                elif op is ScriptOp.MAX:
                    value = max(
                        left,
                        right,
                    )
                elif op is ScriptOp.CMP_EQ:
                    value = (
                        1.0
                        if left == right
                        else 0.0
                    )
                elif op is ScriptOp.CMP_LT:
                    value = (
                        1.0
                        if left < right
                        else 0.0
                    )
                else:
                    value = (
                        1.0
                        if left > right
                        else 0.0
                    )
                registers[dest] = _quantize(
                    self.policy.numeric_mode,
                    value,
                )
            elif op is ScriptOp.CLAMP:
                dest = int(args[0])
                value = registers[
                    int(args[1])
                ]
                lower = registers[
                    int(args[2])
                ]
                upper = registers[
                    int(args[3])
                ]
                if lower > upper:
                    lower, upper = (
                        upper,
                        lower,
                    )
                registers[dest] = _quantize(
                    self.policy.numeric_mode,
                    min(
                        upper,
                        max(
                            lower,
                            value,
                        ),
                    ),
                )
            elif op is ScriptOp.LOAD_STATE:
                registers[
                    int(args[0])
                ] = memory[
                    int(args[1])
                ]
            elif op is ScriptOp.STORE_STATE:
                memory[
                    int(args[0])
                ] = registers[
                    int(args[1])
                ]
            elif op is ScriptOp.JUMP:
                next_pc = int(
                    args[0]
                )
            elif op is ScriptOp.JUMP_IF:
                if registers[
                    int(args[0])
                ] != 0.0:
                    next_pc = int(
                        args[1]
                    )
            elif op is ScriptOp.CALL:
                if (
                    len(call_stack)
                    >= self.policy.call_depth
                ):
                    raise GameEngineLabError(
                        "script call stack exhausted"
                    )
                call_stack.append(
                    pc + 1
                )
                next_pc = int(
                    args[0]
                )
            elif op is ScriptOp.RET:
                if not call_stack:
                    raise GameEngineLabError(
                        "script return with empty call stack"
                    )
                next_pc = call_stack.pop()
            elif op is ScriptOp.EMIT:
                if (
                    len(events)
                    >= self.policy.max_events
                ):
                    raise GameEngineLabError(
                        "script event budget exhausted"
                    )
                events.append(
                    ScriptEvent(
                        str(args[0]),
                        registers[
                            int(args[1])
                        ],
                    )
                )
            elif op is ScriptOp.HALT:
                halted = True
            else:
                raise GameEngineLabError(
                    f"unsupported VM opcode: {op.value}"
                )

            pc = next_pc

        payload = {
            "script_id": script.script_id,
            "era": script.era.value,
            "halted": halted,
            "exhausted": exhausted,
            "steps": steps,
            "registers": registers,
            "state": memory,
            "events": [
                [
                    event.name,
                    event.value,
                ]
                for event in events
            ],
        }
        return ScriptExecution(
            script.script_id,
            script.era,
            halted,
            exhausted,
            steps,
            tuple(registers),
            tuple(memory),
            tuple(events),
            _digest(payload),
        )


@dataclass(frozen=True, slots=True)
class ScriptBuild:
    era: EngineEra
    scripts: tuple[
        CompiledScript,
        ...,
    ]
    manifest_digest: str

    def manifest(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "engine_era": self.era.value,
            "script_count": len(
                self.scripts
            ),
            "scripts": [
                {
                    "script_id":
                        script.script_id,
                    "digest":
                        script.digest,
                    "source_digest":
                        script.source_digest,
                    "dialect":
                        script.dialect,
                }
                for script
                in self.scripts
            ],
            "manifest_digest":
                self.manifest_digest,
            "host_code_execution":
                False,
        }


def compile_script_build(
    era: EngineEra | str,
    sources: Iterable[ScriptSource],
    *,
    compiler: EraScriptCompiler | None = None,
) -> ScriptBuild:
    active = (
        compiler
        or EraScriptCompiler()
    )
    compiled = active.compile_all(
        era,
        tuple(sources),
    )
    key = script_policy(era).era
    identity = {
        "schema_version": 1,
        "engine_era": key.value,
        "scripts": [
            script.document()
            for script
            in compiled
        ],
    }
    return ScriptBuild(
        key,
        compiled,
        _digest(identity),
    )


def script_build_patches(
    build: ScriptBuild,
) -> tuple[SandboxPatch, ...]:
    patches: list[SandboxPatch] = [
        SandboxPatch(
            "scripts/compiled/manifest.json",
            json.dumps(
                build.manifest(),
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
    ]
    for script in build.scripts:
        patches.append(
            SandboxPatch(
                (
                    "scripts/compiled/"
                    + script.script_id
                    + ".script.json"
                ),
                json.dumps(
                    script.document(),
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
            )
        )
    return tuple(patches)


def canonical_script_patches(
    sandbox: RoutedEngineSandbox,
    sources: Iterable[ScriptSource],
) -> tuple[SandboxPatch, ...]:
    build = compile_script_build(
        sandbox.era,
        tuple(sources),
    )
    expected = {
        patch.path: patch.content
        for patch
        in script_build_patches(
            build
        )
    }
    existing = {
        path
        for path in sandbox.tree.files
        if path.startswith(
            "scripts/compiled/"
        )
    }
    patches: list[SandboxPatch] = []
    for path in sorted(
        set(expected) | existing
    ):
        wanted = expected.get(path)
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


def attach_script_build(
    sandbox: RoutedEngineSandbox,
    sources: Iterable[ScriptSource],
) -> RoutedEngineSandbox:
    build = compile_script_build(
        sandbox.era,
        tuple(sources),
    )
    patches = tuple(
        SandboxPatch(
            patch.path,
            patch.content,
            sandbox.tree.file_digest(
                patch.path
            ),
        )
        for patch
        in script_build_patches(
            build
        )
    )
    return sandbox.apply(
        patches
    )


@dataclass(frozen=True, slots=True)
class ScriptProbe:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class ScriptQualityReport:
    era: EngineEra
    probes: tuple[ScriptProbe, ...]

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


class ScriptAdversary:
    """Compile/replay/gas/inventory attestation for the behavior plane."""

    def evaluate(
        self,
        sandbox: RoutedEngineSandbox,
        sources: Iterable[ScriptSource],
    ) -> ScriptQualityReport:
        values = tuple(sources)
        try:
            expected = compile_script_build(
                sandbox.era,
                values,
            )
            manifest = json.loads(
                sandbox.tree.read(
                    "scripts/compiled/manifest.json"
                )
            )
        except (
            GameEngineLabError,
            json.JSONDecodeError,
        ) as exc:
            detail = str(exc)
            return ScriptQualityReport(
                sandbox.era,
                (
                    ScriptProbe(
                        "manifest",
                        False,
                        detail,
                    ),
                    ScriptProbe(
                        "inventory",
                        False,
                        "script build unavailable",
                    ),
                    ScriptProbe(
                        "integrity",
                        False,
                        "script build unavailable",
                    ),
                    ScriptProbe(
                        "determinism",
                        False,
                        "script build unavailable",
                    ),
                    ScriptProbe(
                        "gas",
                        False,
                        "script build unavailable",
                    ),
                ),
            )

        manifest_ok = (
            manifest
            == expected.manifest()
        )
        expected_paths = {
            patch.path
            for patch
            in script_build_patches(
                expected
            )
        }
        actual_paths = {
            path
            for path
            in sandbox.tree.files
            if path.startswith(
                "scripts/compiled/"
            )
        }
        inventory_ok = (
            expected_paths
            == actual_paths
        )

        integrity = True
        for script in expected.scripts:
            path = (
                "scripts/compiled/"
                + script.script_id
                + ".script.json"
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
                integrity = False
                break
            if document != script.document():
                integrity = False
                break

        deterministic = True
        gas_ok = True
        vm = ScriptVM(
            sandbox.era
        )
        for script in expected.scripts:
            first = vm.run(
                script,
                inputs=(1.0, 2.0),
            )
            second = vm.run(
                script,
                inputs=(1.0, 2.0),
            )
            if first != second:
                deterministic = False
            if (
                first.exhausted
                or first.steps
                > script_policy(
                    sandbox.era
                ).max_steps
            ):
                gas_ok = False

        return ScriptQualityReport(
            sandbox.era,
            (
                ScriptProbe(
                    "manifest",
                    manifest_ok,
                    "canonical script manifest",
                ),
                ScriptProbe(
                    "inventory",
                    inventory_ok,
                    "exact compiled script inventory",
                ),
                ScriptProbe(
                    "integrity",
                    integrity,
                    "compiled script bytecode attested",
                ),
                ScriptProbe(
                    "determinism",
                    deterministic,
                    "replay-stable VM execution",
                ),
                ScriptProbe(
                    "gas",
                    gas_ok,
                    "bounded instruction execution",
                ),
            ),
        )


def canonical_script_sources(
    era: EngineEra | str,
) -> tuple[ScriptSource, ...]:
    """Return a tiny era-valid behavior pack used by project sandboxes."""

    policy = script_policy(
        era
    )
    movement = ScriptSource(
        "player_motion",
        (
            ScriptInstruction(
                ScriptOp.LOAD_STATE,
                (0, 0),
            ),
            ScriptInstruction(
                ScriptOp.CONST,
                (1, 1.0),
            ),
            ScriptInstruction(
                ScriptOp.ADD,
                (0, 0, 1),
            ),
            ScriptInstruction(
                ScriptOp.STORE_STATE,
                (0, 0),
            ),
            ScriptInstruction(
                ScriptOp.EMIT,
                ("moved", 0),
            ),
            ScriptInstruction(
                ScriptOp.HALT,
            ),
        ),
    )
    sources = [movement]

    if ScriptOp.JUMP_IF in policy.allowed:
        threshold = ScriptSource(
            "threshold_event",
            (
                ScriptInstruction(
                    ScriptOp.CONST,
                    (0, 2.0),
                ),
                ScriptInstruction(
                    ScriptOp.CONST,
                    (1, 1.0),
                ),
                ScriptInstruction(
                    ScriptOp.CMP_LT,
                    (2, 1, 0),
                ),
                ScriptInstruction(
                    ScriptOp.JUMP_IF,
                    (2, 5),
                ),
                ScriptInstruction(
                    ScriptOp.HALT,
                ),
                ScriptInstruction(
                    ScriptOp.EMIT,
                    ("threshold", 2),
                ),
                ScriptInstruction(
                    ScriptOp.HALT,
                ),
            ),
        )
        sources.append(
            threshold
        )

    if (
        ScriptOp.CALL in policy.allowed
        and policy.call_depth > 0
    ):
        call_program = ScriptSource(
            "call_event",
            (
                ScriptInstruction(
                    ScriptOp.CALL,
                    (3,),
                ),
                ScriptInstruction(
                    ScriptOp.EMIT,
                    ("returned", 0),
                ),
                ScriptInstruction(
                    ScriptOp.HALT,
                ),
                ScriptInstruction(
                    ScriptOp.CONST,
                    (0, 3.0),
                ),
                ScriptInstruction(
                    ScriptOp.RET,
                ),
                ScriptInstruction(
                    ScriptOp.HALT,
                ),
            ),
        )
        sources.append(
            call_program
        )

    return tuple(sources)
