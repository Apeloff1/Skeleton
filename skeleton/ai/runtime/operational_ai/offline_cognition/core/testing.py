"""Run domain-specific positive and adversarial cases against actual core algorithms.

A production model may never be substituted with this test-only FakeWorker.
Tests run against source-bound transforms and real temporary SQLite metadata.

Every test-family operation is selected from a closed literal import registry.
The registry is lazy: no family implementation is imported until selected.
"""
from __future__ import annotations
import importlib
import tempfile
from types import MappingProxyType
from .contracts import Scope,CognitionError,hash_bytes
from .profiles import read_profile

# Source-bound inventory: 64 canonical families x 20 allowed operations.
# Every import_module argument is a literal; never interpolate untrusted
# family or operation identifiers into a module path.
_MODULE_LOADERS = MappingProxyType({
    ("tokenizer_bridge", "source"): lambda: importlib.import_module(
        ".families.tokenizer_bridge.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tokenizer_bridge", "search"): lambda: importlib.import_module(
        ".families.tokenizer_bridge.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tokenizer_bridge", "fusion"): lambda: importlib.import_module(
        ".families.tokenizer_bridge.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tokenizer_bridge", "rank"): lambda: importlib.import_module(
        ".families.tokenizer_bridge.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tokenizer_bridge", "context"): lambda: importlib.import_module(
        ".families.tokenizer_bridge.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tokenizer_bridge", "plan"): lambda: importlib.import_module(
        ".families.tokenizer_bridge.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tokenizer_bridge", "resource"): lambda: importlib.import_module(
        ".families.tokenizer_bridge.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tokenizer_bridge", "schedule"): lambda: importlib.import_module(
        ".families.tokenizer_bridge.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tokenizer_bridge", "permission"): lambda: importlib.import_module(
        ".families.tokenizer_bridge.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tokenizer_bridge", "native"): lambda: importlib.import_module(
        ".families.tokenizer_bridge.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tokenizer_bridge", "replay"): lambda: importlib.import_module(
        ".families.tokenizer_bridge.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tokenizer_bridge", "memory"): lambda: importlib.import_module(
        ".families.tokenizer_bridge.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tokenizer_bridge", "privacy"): lambda: importlib.import_module(
        ".families.tokenizer_bridge.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tokenizer_bridge", "evaluate"): lambda: importlib.import_module(
        ".families.tokenizer_bridge.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tokenizer_bridge", "audit"): lambda: importlib.import_module(
        ".families.tokenizer_bridge.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tokenizer_bridge", "recover"): lambda: importlib.import_module(
        ".families.tokenizer_bridge.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tokenizer_bridge", "stream"): lambda: importlib.import_module(
        ".families.tokenizer_bridge.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tokenizer_bridge", "tool"): lambda: importlib.import_module(
        ".families.tokenizer_bridge.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tokenizer_bridge", "checkpoint"): lambda: importlib.import_module(
        ".families.tokenizer_bridge.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tokenizer_bridge", "health"): lambda: importlib.import_module(
        ".families.tokenizer_bridge.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("sampler_control", "source"): lambda: importlib.import_module(
        ".families.sampler_control.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("sampler_control", "search"): lambda: importlib.import_module(
        ".families.sampler_control.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("sampler_control", "fusion"): lambda: importlib.import_module(
        ".families.sampler_control.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("sampler_control", "rank"): lambda: importlib.import_module(
        ".families.sampler_control.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("sampler_control", "context"): lambda: importlib.import_module(
        ".families.sampler_control.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("sampler_control", "plan"): lambda: importlib.import_module(
        ".families.sampler_control.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("sampler_control", "resource"): lambda: importlib.import_module(
        ".families.sampler_control.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("sampler_control", "schedule"): lambda: importlib.import_module(
        ".families.sampler_control.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("sampler_control", "permission"): lambda: importlib.import_module(
        ".families.sampler_control.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("sampler_control", "native"): lambda: importlib.import_module(
        ".families.sampler_control.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("sampler_control", "replay"): lambda: importlib.import_module(
        ".families.sampler_control.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("sampler_control", "memory"): lambda: importlib.import_module(
        ".families.sampler_control.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("sampler_control", "privacy"): lambda: importlib.import_module(
        ".families.sampler_control.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("sampler_control", "evaluate"): lambda: importlib.import_module(
        ".families.sampler_control.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("sampler_control", "audit"): lambda: importlib.import_module(
        ".families.sampler_control.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("sampler_control", "recover"): lambda: importlib.import_module(
        ".families.sampler_control.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("sampler_control", "stream"): lambda: importlib.import_module(
        ".families.sampler_control.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("sampler_control", "tool"): lambda: importlib.import_module(
        ".families.sampler_control.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("sampler_control", "checkpoint"): lambda: importlib.import_module(
        ".families.sampler_control.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("sampler_control", "health"): lambda: importlib.import_module(
        ".families.sampler_control.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("stream_commit", "source"): lambda: importlib.import_module(
        ".families.stream_commit.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("stream_commit", "search"): lambda: importlib.import_module(
        ".families.stream_commit.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("stream_commit", "fusion"): lambda: importlib.import_module(
        ".families.stream_commit.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("stream_commit", "rank"): lambda: importlib.import_module(
        ".families.stream_commit.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("stream_commit", "context"): lambda: importlib.import_module(
        ".families.stream_commit.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("stream_commit", "plan"): lambda: importlib.import_module(
        ".families.stream_commit.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("stream_commit", "resource"): lambda: importlib.import_module(
        ".families.stream_commit.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("stream_commit", "schedule"): lambda: importlib.import_module(
        ".families.stream_commit.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("stream_commit", "permission"): lambda: importlib.import_module(
        ".families.stream_commit.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("stream_commit", "native"): lambda: importlib.import_module(
        ".families.stream_commit.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("stream_commit", "replay"): lambda: importlib.import_module(
        ".families.stream_commit.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("stream_commit", "memory"): lambda: importlib.import_module(
        ".families.stream_commit.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("stream_commit", "privacy"): lambda: importlib.import_module(
        ".families.stream_commit.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("stream_commit", "evaluate"): lambda: importlib.import_module(
        ".families.stream_commit.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("stream_commit", "audit"): lambda: importlib.import_module(
        ".families.stream_commit.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("stream_commit", "recover"): lambda: importlib.import_module(
        ".families.stream_commit.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("stream_commit", "stream"): lambda: importlib.import_module(
        ".families.stream_commit.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("stream_commit", "tool"): lambda: importlib.import_module(
        ".families.stream_commit.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("stream_commit", "checkpoint"): lambda: importlib.import_module(
        ".families.stream_commit.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("stream_commit", "health"): lambda: importlib.import_module(
        ".families.stream_commit.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("checkpoint_adapter", "source"): lambda: importlib.import_module(
        ".families.checkpoint_adapter.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("checkpoint_adapter", "search"): lambda: importlib.import_module(
        ".families.checkpoint_adapter.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("checkpoint_adapter", "fusion"): lambda: importlib.import_module(
        ".families.checkpoint_adapter.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("checkpoint_adapter", "rank"): lambda: importlib.import_module(
        ".families.checkpoint_adapter.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("checkpoint_adapter", "context"): lambda: importlib.import_module(
        ".families.checkpoint_adapter.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("checkpoint_adapter", "plan"): lambda: importlib.import_module(
        ".families.checkpoint_adapter.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("checkpoint_adapter", "resource"): lambda: importlib.import_module(
        ".families.checkpoint_adapter.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("checkpoint_adapter", "schedule"): lambda: importlib.import_module(
        ".families.checkpoint_adapter.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("checkpoint_adapter", "permission"): lambda: importlib.import_module(
        ".families.checkpoint_adapter.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("checkpoint_adapter", "native"): lambda: importlib.import_module(
        ".families.checkpoint_adapter.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("checkpoint_adapter", "replay"): lambda: importlib.import_module(
        ".families.checkpoint_adapter.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("checkpoint_adapter", "memory"): lambda: importlib.import_module(
        ".families.checkpoint_adapter.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("checkpoint_adapter", "privacy"): lambda: importlib.import_module(
        ".families.checkpoint_adapter.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("checkpoint_adapter", "evaluate"): lambda: importlib.import_module(
        ".families.checkpoint_adapter.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("checkpoint_adapter", "audit"): lambda: importlib.import_module(
        ".families.checkpoint_adapter.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("checkpoint_adapter", "recover"): lambda: importlib.import_module(
        ".families.checkpoint_adapter.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("checkpoint_adapter", "stream"): lambda: importlib.import_module(
        ".families.checkpoint_adapter.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("checkpoint_adapter", "tool"): lambda: importlib.import_module(
        ".families.checkpoint_adapter.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("checkpoint_adapter", "checkpoint"): lambda: importlib.import_module(
        ".families.checkpoint_adapter.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("checkpoint_adapter", "health"): lambda: importlib.import_module(
        ".families.checkpoint_adapter.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("gpu_pressure", "source"): lambda: importlib.import_module(
        ".families.gpu_pressure.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("gpu_pressure", "search"): lambda: importlib.import_module(
        ".families.gpu_pressure.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("gpu_pressure", "fusion"): lambda: importlib.import_module(
        ".families.gpu_pressure.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("gpu_pressure", "rank"): lambda: importlib.import_module(
        ".families.gpu_pressure.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("gpu_pressure", "context"): lambda: importlib.import_module(
        ".families.gpu_pressure.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("gpu_pressure", "plan"): lambda: importlib.import_module(
        ".families.gpu_pressure.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("gpu_pressure", "resource"): lambda: importlib.import_module(
        ".families.gpu_pressure.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("gpu_pressure", "schedule"): lambda: importlib.import_module(
        ".families.gpu_pressure.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("gpu_pressure", "permission"): lambda: importlib.import_module(
        ".families.gpu_pressure.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("gpu_pressure", "native"): lambda: importlib.import_module(
        ".families.gpu_pressure.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("gpu_pressure", "replay"): lambda: importlib.import_module(
        ".families.gpu_pressure.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("gpu_pressure", "memory"): lambda: importlib.import_module(
        ".families.gpu_pressure.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("gpu_pressure", "privacy"): lambda: importlib.import_module(
        ".families.gpu_pressure.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("gpu_pressure", "evaluate"): lambda: importlib.import_module(
        ".families.gpu_pressure.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("gpu_pressure", "audit"): lambda: importlib.import_module(
        ".families.gpu_pressure.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("gpu_pressure", "recover"): lambda: importlib.import_module(
        ".families.gpu_pressure.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("gpu_pressure", "stream"): lambda: importlib.import_module(
        ".families.gpu_pressure.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("gpu_pressure", "tool"): lambda: importlib.import_module(
        ".families.gpu_pressure.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("gpu_pressure", "checkpoint"): lambda: importlib.import_module(
        ".families.gpu_pressure.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("gpu_pressure", "health"): lambda: importlib.import_module(
        ".families.gpu_pressure.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cpu_fallback", "source"): lambda: importlib.import_module(
        ".families.cpu_fallback.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cpu_fallback", "search"): lambda: importlib.import_module(
        ".families.cpu_fallback.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cpu_fallback", "fusion"): lambda: importlib.import_module(
        ".families.cpu_fallback.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cpu_fallback", "rank"): lambda: importlib.import_module(
        ".families.cpu_fallback.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cpu_fallback", "context"): lambda: importlib.import_module(
        ".families.cpu_fallback.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cpu_fallback", "plan"): lambda: importlib.import_module(
        ".families.cpu_fallback.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cpu_fallback", "resource"): lambda: importlib.import_module(
        ".families.cpu_fallback.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cpu_fallback", "schedule"): lambda: importlib.import_module(
        ".families.cpu_fallback.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cpu_fallback", "permission"): lambda: importlib.import_module(
        ".families.cpu_fallback.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cpu_fallback", "native"): lambda: importlib.import_module(
        ".families.cpu_fallback.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cpu_fallback", "replay"): lambda: importlib.import_module(
        ".families.cpu_fallback.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cpu_fallback", "memory"): lambda: importlib.import_module(
        ".families.cpu_fallback.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cpu_fallback", "privacy"): lambda: importlib.import_module(
        ".families.cpu_fallback.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cpu_fallback", "evaluate"): lambda: importlib.import_module(
        ".families.cpu_fallback.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cpu_fallback", "audit"): lambda: importlib.import_module(
        ".families.cpu_fallback.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cpu_fallback", "recover"): lambda: importlib.import_module(
        ".families.cpu_fallback.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cpu_fallback", "stream"): lambda: importlib.import_module(
        ".families.cpu_fallback.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cpu_fallback", "tool"): lambda: importlib.import_module(
        ".families.cpu_fallback.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cpu_fallback", "checkpoint"): lambda: importlib.import_module(
        ".families.cpu_fallback.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cpu_fallback", "health"): lambda: importlib.import_module(
        ".families.cpu_fallback.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("prompt_reservation", "source"): lambda: importlib.import_module(
        ".families.prompt_reservation.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("prompt_reservation", "search"): lambda: importlib.import_module(
        ".families.prompt_reservation.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("prompt_reservation", "fusion"): lambda: importlib.import_module(
        ".families.prompt_reservation.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("prompt_reservation", "rank"): lambda: importlib.import_module(
        ".families.prompt_reservation.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("prompt_reservation", "context"): lambda: importlib.import_module(
        ".families.prompt_reservation.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("prompt_reservation", "plan"): lambda: importlib.import_module(
        ".families.prompt_reservation.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("prompt_reservation", "resource"): lambda: importlib.import_module(
        ".families.prompt_reservation.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("prompt_reservation", "schedule"): lambda: importlib.import_module(
        ".families.prompt_reservation.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("prompt_reservation", "permission"): lambda: importlib.import_module(
        ".families.prompt_reservation.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("prompt_reservation", "native"): lambda: importlib.import_module(
        ".families.prompt_reservation.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("prompt_reservation", "replay"): lambda: importlib.import_module(
        ".families.prompt_reservation.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("prompt_reservation", "memory"): lambda: importlib.import_module(
        ".families.prompt_reservation.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("prompt_reservation", "privacy"): lambda: importlib.import_module(
        ".families.prompt_reservation.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("prompt_reservation", "evaluate"): lambda: importlib.import_module(
        ".families.prompt_reservation.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("prompt_reservation", "audit"): lambda: importlib.import_module(
        ".families.prompt_reservation.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("prompt_reservation", "recover"): lambda: importlib.import_module(
        ".families.prompt_reservation.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("prompt_reservation", "stream"): lambda: importlib.import_module(
        ".families.prompt_reservation.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("prompt_reservation", "tool"): lambda: importlib.import_module(
        ".families.prompt_reservation.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("prompt_reservation", "checkpoint"): lambda: importlib.import_module(
        ".families.prompt_reservation.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("prompt_reservation", "health"): lambda: importlib.import_module(
        ".families.prompt_reservation.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_limit", "source"): lambda: importlib.import_module(
        ".families.token_limit.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_limit", "search"): lambda: importlib.import_module(
        ".families.token_limit.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_limit", "fusion"): lambda: importlib.import_module(
        ".families.token_limit.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_limit", "rank"): lambda: importlib.import_module(
        ".families.token_limit.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_limit", "context"): lambda: importlib.import_module(
        ".families.token_limit.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_limit", "plan"): lambda: importlib.import_module(
        ".families.token_limit.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_limit", "resource"): lambda: importlib.import_module(
        ".families.token_limit.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_limit", "schedule"): lambda: importlib.import_module(
        ".families.token_limit.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_limit", "permission"): lambda: importlib.import_module(
        ".families.token_limit.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_limit", "native"): lambda: importlib.import_module(
        ".families.token_limit.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_limit", "replay"): lambda: importlib.import_module(
        ".families.token_limit.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_limit", "memory"): lambda: importlib.import_module(
        ".families.token_limit.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_limit", "privacy"): lambda: importlib.import_module(
        ".families.token_limit.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_limit", "evaluate"): lambda: importlib.import_module(
        ".families.token_limit.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_limit", "audit"): lambda: importlib.import_module(
        ".families.token_limit.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_limit", "recover"): lambda: importlib.import_module(
        ".families.token_limit.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_limit", "stream"): lambda: importlib.import_module(
        ".families.token_limit.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_limit", "tool"): lambda: importlib.import_module(
        ".families.token_limit.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_limit", "checkpoint"): lambda: importlib.import_module(
        ".families.token_limit.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_limit", "health"): lambda: importlib.import_module(
        ".families.token_limit.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("history_projection", "source"): lambda: importlib.import_module(
        ".families.history_projection.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("history_projection", "search"): lambda: importlib.import_module(
        ".families.history_projection.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("history_projection", "fusion"): lambda: importlib.import_module(
        ".families.history_projection.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("history_projection", "rank"): lambda: importlib.import_module(
        ".families.history_projection.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("history_projection", "context"): lambda: importlib.import_module(
        ".families.history_projection.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("history_projection", "plan"): lambda: importlib.import_module(
        ".families.history_projection.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("history_projection", "resource"): lambda: importlib.import_module(
        ".families.history_projection.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("history_projection", "schedule"): lambda: importlib.import_module(
        ".families.history_projection.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("history_projection", "permission"): lambda: importlib.import_module(
        ".families.history_projection.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("history_projection", "native"): lambda: importlib.import_module(
        ".families.history_projection.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("history_projection", "replay"): lambda: importlib.import_module(
        ".families.history_projection.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("history_projection", "memory"): lambda: importlib.import_module(
        ".families.history_projection.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("history_projection", "privacy"): lambda: importlib.import_module(
        ".families.history_projection.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("history_projection", "evaluate"): lambda: importlib.import_module(
        ".families.history_projection.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("history_projection", "audit"): lambda: importlib.import_module(
        ".families.history_projection.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("history_projection", "recover"): lambda: importlib.import_module(
        ".families.history_projection.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("history_projection", "stream"): lambda: importlib.import_module(
        ".families.history_projection.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("history_projection", "tool"): lambda: importlib.import_module(
        ".families.history_projection.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("history_projection", "checkpoint"): lambda: importlib.import_module(
        ".families.history_projection.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("history_projection", "health"): lambda: importlib.import_module(
        ".families.history_projection.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("system_policy", "source"): lambda: importlib.import_module(
        ".families.system_policy.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("system_policy", "search"): lambda: importlib.import_module(
        ".families.system_policy.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("system_policy", "fusion"): lambda: importlib.import_module(
        ".families.system_policy.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("system_policy", "rank"): lambda: importlib.import_module(
        ".families.system_policy.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("system_policy", "context"): lambda: importlib.import_module(
        ".families.system_policy.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("system_policy", "plan"): lambda: importlib.import_module(
        ".families.system_policy.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("system_policy", "resource"): lambda: importlib.import_module(
        ".families.system_policy.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("system_policy", "schedule"): lambda: importlib.import_module(
        ".families.system_policy.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("system_policy", "permission"): lambda: importlib.import_module(
        ".families.system_policy.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("system_policy", "native"): lambda: importlib.import_module(
        ".families.system_policy.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("system_policy", "replay"): lambda: importlib.import_module(
        ".families.system_policy.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("system_policy", "memory"): lambda: importlib.import_module(
        ".families.system_policy.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("system_policy", "privacy"): lambda: importlib.import_module(
        ".families.system_policy.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("system_policy", "evaluate"): lambda: importlib.import_module(
        ".families.system_policy.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("system_policy", "audit"): lambda: importlib.import_module(
        ".families.system_policy.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("system_policy", "recover"): lambda: importlib.import_module(
        ".families.system_policy.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("system_policy", "stream"): lambda: importlib.import_module(
        ".families.system_policy.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("system_policy", "tool"): lambda: importlib.import_module(
        ".families.system_policy.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("system_policy", "checkpoint"): lambda: importlib.import_module(
        ".families.system_policy.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("system_policy", "health"): lambda: importlib.import_module(
        ".families.system_policy.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("turn_packing", "source"): lambda: importlib.import_module(
        ".families.turn_packing.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("turn_packing", "search"): lambda: importlib.import_module(
        ".families.turn_packing.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("turn_packing", "fusion"): lambda: importlib.import_module(
        ".families.turn_packing.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("turn_packing", "rank"): lambda: importlib.import_module(
        ".families.turn_packing.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("turn_packing", "context"): lambda: importlib.import_module(
        ".families.turn_packing.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("turn_packing", "plan"): lambda: importlib.import_module(
        ".families.turn_packing.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("turn_packing", "resource"): lambda: importlib.import_module(
        ".families.turn_packing.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("turn_packing", "schedule"): lambda: importlib.import_module(
        ".families.turn_packing.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("turn_packing", "permission"): lambda: importlib.import_module(
        ".families.turn_packing.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("turn_packing", "native"): lambda: importlib.import_module(
        ".families.turn_packing.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("turn_packing", "replay"): lambda: importlib.import_module(
        ".families.turn_packing.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("turn_packing", "memory"): lambda: importlib.import_module(
        ".families.turn_packing.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("turn_packing", "privacy"): lambda: importlib.import_module(
        ".families.turn_packing.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("turn_packing", "evaluate"): lambda: importlib.import_module(
        ".families.turn_packing.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("turn_packing", "audit"): lambda: importlib.import_module(
        ".families.turn_packing.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("turn_packing", "recover"): lambda: importlib.import_module(
        ".families.turn_packing.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("turn_packing", "stream"): lambda: importlib.import_module(
        ".families.turn_packing.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("turn_packing", "tool"): lambda: importlib.import_module(
        ".families.turn_packing.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("turn_packing", "checkpoint"): lambda: importlib.import_module(
        ".families.turn_packing.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("turn_packing", "health"): lambda: importlib.import_module(
        ".families.turn_packing.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retrieval_insertion", "source"): lambda: importlib.import_module(
        ".families.retrieval_insertion.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retrieval_insertion", "search"): lambda: importlib.import_module(
        ".families.retrieval_insertion.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retrieval_insertion", "fusion"): lambda: importlib.import_module(
        ".families.retrieval_insertion.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retrieval_insertion", "rank"): lambda: importlib.import_module(
        ".families.retrieval_insertion.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retrieval_insertion", "context"): lambda: importlib.import_module(
        ".families.retrieval_insertion.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retrieval_insertion", "plan"): lambda: importlib.import_module(
        ".families.retrieval_insertion.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retrieval_insertion", "resource"): lambda: importlib.import_module(
        ".families.retrieval_insertion.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retrieval_insertion", "schedule"): lambda: importlib.import_module(
        ".families.retrieval_insertion.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retrieval_insertion", "permission"): lambda: importlib.import_module(
        ".families.retrieval_insertion.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retrieval_insertion", "native"): lambda: importlib.import_module(
        ".families.retrieval_insertion.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retrieval_insertion", "replay"): lambda: importlib.import_module(
        ".families.retrieval_insertion.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retrieval_insertion", "memory"): lambda: importlib.import_module(
        ".families.retrieval_insertion.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retrieval_insertion", "privacy"): lambda: importlib.import_module(
        ".families.retrieval_insertion.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retrieval_insertion", "evaluate"): lambda: importlib.import_module(
        ".families.retrieval_insertion.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retrieval_insertion", "audit"): lambda: importlib.import_module(
        ".families.retrieval_insertion.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retrieval_insertion", "recover"): lambda: importlib.import_module(
        ".families.retrieval_insertion.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retrieval_insertion", "stream"): lambda: importlib.import_module(
        ".families.retrieval_insertion.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retrieval_insertion", "tool"): lambda: importlib.import_module(
        ".families.retrieval_insertion.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retrieval_insertion", "checkpoint"): lambda: importlib.import_module(
        ".families.retrieval_insertion.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retrieval_insertion", "health"): lambda: importlib.import_module(
        ".families.retrieval_insertion.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_digest", "source"): lambda: importlib.import_module(
        ".families.context_digest.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_digest", "search"): lambda: importlib.import_module(
        ".families.context_digest.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_digest", "fusion"): lambda: importlib.import_module(
        ".families.context_digest.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_digest", "rank"): lambda: importlib.import_module(
        ".families.context_digest.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_digest", "context"): lambda: importlib.import_module(
        ".families.context_digest.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_digest", "plan"): lambda: importlib.import_module(
        ".families.context_digest.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_digest", "resource"): lambda: importlib.import_module(
        ".families.context_digest.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_digest", "schedule"): lambda: importlib.import_module(
        ".families.context_digest.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_digest", "permission"): lambda: importlib.import_module(
        ".families.context_digest.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_digest", "native"): lambda: importlib.import_module(
        ".families.context_digest.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_digest", "replay"): lambda: importlib.import_module(
        ".families.context_digest.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_digest", "memory"): lambda: importlib.import_module(
        ".families.context_digest.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_digest", "privacy"): lambda: importlib.import_module(
        ".families.context_digest.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_digest", "evaluate"): lambda: importlib.import_module(
        ".families.context_digest.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_digest", "audit"): lambda: importlib.import_module(
        ".families.context_digest.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_digest", "recover"): lambda: importlib.import_module(
        ".families.context_digest.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_digest", "stream"): lambda: importlib.import_module(
        ".families.context_digest.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_digest", "tool"): lambda: importlib.import_module(
        ".families.context_digest.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_digest", "checkpoint"): lambda: importlib.import_module(
        ".families.context_digest.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_digest", "health"): lambda: importlib.import_module(
        ".families.context_digest.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_compaction", "source"): lambda: importlib.import_module(
        ".families.context_compaction.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_compaction", "search"): lambda: importlib.import_module(
        ".families.context_compaction.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_compaction", "fusion"): lambda: importlib.import_module(
        ".families.context_compaction.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_compaction", "rank"): lambda: importlib.import_module(
        ".families.context_compaction.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_compaction", "context"): lambda: importlib.import_module(
        ".families.context_compaction.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_compaction", "plan"): lambda: importlib.import_module(
        ".families.context_compaction.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_compaction", "resource"): lambda: importlib.import_module(
        ".families.context_compaction.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_compaction", "schedule"): lambda: importlib.import_module(
        ".families.context_compaction.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_compaction", "permission"): lambda: importlib.import_module(
        ".families.context_compaction.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_compaction", "native"): lambda: importlib.import_module(
        ".families.context_compaction.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_compaction", "replay"): lambda: importlib.import_module(
        ".families.context_compaction.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_compaction", "memory"): lambda: importlib.import_module(
        ".families.context_compaction.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_compaction", "privacy"): lambda: importlib.import_module(
        ".families.context_compaction.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_compaction", "evaluate"): lambda: importlib.import_module(
        ".families.context_compaction.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_compaction", "audit"): lambda: importlib.import_module(
        ".families.context_compaction.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_compaction", "recover"): lambda: importlib.import_module(
        ".families.context_compaction.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_compaction", "stream"): lambda: importlib.import_module(
        ".families.context_compaction.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_compaction", "tool"): lambda: importlib.import_module(
        ".families.context_compaction.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_compaction", "checkpoint"): lambda: importlib.import_module(
        ".families.context_compaction.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("context_compaction", "health"): lambda: importlib.import_module(
        ".families.context_compaction.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("overflow_hold", "source"): lambda: importlib.import_module(
        ".families.overflow_hold.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("overflow_hold", "search"): lambda: importlib.import_module(
        ".families.overflow_hold.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("overflow_hold", "fusion"): lambda: importlib.import_module(
        ".families.overflow_hold.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("overflow_hold", "rank"): lambda: importlib.import_module(
        ".families.overflow_hold.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("overflow_hold", "context"): lambda: importlib.import_module(
        ".families.overflow_hold.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("overflow_hold", "plan"): lambda: importlib.import_module(
        ".families.overflow_hold.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("overflow_hold", "resource"): lambda: importlib.import_module(
        ".families.overflow_hold.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("overflow_hold", "schedule"): lambda: importlib.import_module(
        ".families.overflow_hold.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("overflow_hold", "permission"): lambda: importlib.import_module(
        ".families.overflow_hold.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("overflow_hold", "native"): lambda: importlib.import_module(
        ".families.overflow_hold.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("overflow_hold", "replay"): lambda: importlib.import_module(
        ".families.overflow_hold.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("overflow_hold", "memory"): lambda: importlib.import_module(
        ".families.overflow_hold.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("overflow_hold", "privacy"): lambda: importlib.import_module(
        ".families.overflow_hold.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("overflow_hold", "evaluate"): lambda: importlib.import_module(
        ".families.overflow_hold.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("overflow_hold", "audit"): lambda: importlib.import_module(
        ".families.overflow_hold.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("overflow_hold", "recover"): lambda: importlib.import_module(
        ".families.overflow_hold.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("overflow_hold", "stream"): lambda: importlib.import_module(
        ".families.overflow_hold.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("overflow_hold", "tool"): lambda: importlib.import_module(
        ".families.overflow_hold.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("overflow_hold", "checkpoint"): lambda: importlib.import_module(
        ".families.overflow_hold.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("overflow_hold", "health"): lambda: importlib.import_module(
        ".families.overflow_hold.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("window_allocator", "source"): lambda: importlib.import_module(
        ".families.window_allocator.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("window_allocator", "search"): lambda: importlib.import_module(
        ".families.window_allocator.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("window_allocator", "fusion"): lambda: importlib.import_module(
        ".families.window_allocator.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("window_allocator", "rank"): lambda: importlib.import_module(
        ".families.window_allocator.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("window_allocator", "context"): lambda: importlib.import_module(
        ".families.window_allocator.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("window_allocator", "plan"): lambda: importlib.import_module(
        ".families.window_allocator.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("window_allocator", "resource"): lambda: importlib.import_module(
        ".families.window_allocator.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("window_allocator", "schedule"): lambda: importlib.import_module(
        ".families.window_allocator.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("window_allocator", "permission"): lambda: importlib.import_module(
        ".families.window_allocator.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("window_allocator", "native"): lambda: importlib.import_module(
        ".families.window_allocator.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("window_allocator", "replay"): lambda: importlib.import_module(
        ".families.window_allocator.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("window_allocator", "memory"): lambda: importlib.import_module(
        ".families.window_allocator.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("window_allocator", "privacy"): lambda: importlib.import_module(
        ".families.window_allocator.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("window_allocator", "evaluate"): lambda: importlib.import_module(
        ".families.window_allocator.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("window_allocator", "audit"): lambda: importlib.import_module(
        ".families.window_allocator.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("window_allocator", "recover"): lambda: importlib.import_module(
        ".families.window_allocator.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("window_allocator", "stream"): lambda: importlib.import_module(
        ".families.window_allocator.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("window_allocator", "tool"): lambda: importlib.import_module(
        ".families.window_allocator.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("window_allocator", "checkpoint"): lambda: importlib.import_module(
        ".families.window_allocator.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("window_allocator", "health"): lambda: importlib.import_module(
        ".families.window_allocator.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("consent_custody", "source"): lambda: importlib.import_module(
        ".families.consent_custody.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("consent_custody", "search"): lambda: importlib.import_module(
        ".families.consent_custody.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("consent_custody", "fusion"): lambda: importlib.import_module(
        ".families.consent_custody.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("consent_custody", "rank"): lambda: importlib.import_module(
        ".families.consent_custody.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("consent_custody", "context"): lambda: importlib.import_module(
        ".families.consent_custody.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("consent_custody", "plan"): lambda: importlib.import_module(
        ".families.consent_custody.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("consent_custody", "resource"): lambda: importlib.import_module(
        ".families.consent_custody.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("consent_custody", "schedule"): lambda: importlib.import_module(
        ".families.consent_custody.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("consent_custody", "permission"): lambda: importlib.import_module(
        ".families.consent_custody.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("consent_custody", "native"): lambda: importlib.import_module(
        ".families.consent_custody.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("consent_custody", "replay"): lambda: importlib.import_module(
        ".families.consent_custody.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("consent_custody", "memory"): lambda: importlib.import_module(
        ".families.consent_custody.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("consent_custody", "privacy"): lambda: importlib.import_module(
        ".families.consent_custody.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("consent_custody", "evaluate"): lambda: importlib.import_module(
        ".families.consent_custody.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("consent_custody", "audit"): lambda: importlib.import_module(
        ".families.consent_custody.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("consent_custody", "recover"): lambda: importlib.import_module(
        ".families.consent_custody.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("consent_custody", "stream"): lambda: importlib.import_module(
        ".families.consent_custody.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("consent_custody", "tool"): lambda: importlib.import_module(
        ".families.consent_custody.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("consent_custody", "checkpoint"): lambda: importlib.import_module(
        ".families.consent_custody.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("consent_custody", "health"): lambda: importlib.import_module(
        ".families.consent_custody.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("recall_catalog", "source"): lambda: importlib.import_module(
        ".families.recall_catalog.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("recall_catalog", "search"): lambda: importlib.import_module(
        ".families.recall_catalog.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("recall_catalog", "fusion"): lambda: importlib.import_module(
        ".families.recall_catalog.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("recall_catalog", "rank"): lambda: importlib.import_module(
        ".families.recall_catalog.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("recall_catalog", "context"): lambda: importlib.import_module(
        ".families.recall_catalog.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("recall_catalog", "plan"): lambda: importlib.import_module(
        ".families.recall_catalog.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("recall_catalog", "resource"): lambda: importlib.import_module(
        ".families.recall_catalog.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("recall_catalog", "schedule"): lambda: importlib.import_module(
        ".families.recall_catalog.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("recall_catalog", "permission"): lambda: importlib.import_module(
        ".families.recall_catalog.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("recall_catalog", "native"): lambda: importlib.import_module(
        ".families.recall_catalog.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("recall_catalog", "replay"): lambda: importlib.import_module(
        ".families.recall_catalog.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("recall_catalog", "memory"): lambda: importlib.import_module(
        ".families.recall_catalog.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("recall_catalog", "privacy"): lambda: importlib.import_module(
        ".families.recall_catalog.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("recall_catalog", "evaluate"): lambda: importlib.import_module(
        ".families.recall_catalog.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("recall_catalog", "audit"): lambda: importlib.import_module(
        ".families.recall_catalog.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("recall_catalog", "recover"): lambda: importlib.import_module(
        ".families.recall_catalog.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("recall_catalog", "stream"): lambda: importlib.import_module(
        ".families.recall_catalog.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("recall_catalog", "tool"): lambda: importlib.import_module(
        ".families.recall_catalog.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("recall_catalog", "checkpoint"): lambda: importlib.import_module(
        ".families.recall_catalog.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("recall_catalog", "health"): lambda: importlib.import_module(
        ".families.recall_catalog.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_retraction", "source"): lambda: importlib.import_module(
        ".families.source_retraction.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_retraction", "search"): lambda: importlib.import_module(
        ".families.source_retraction.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_retraction", "fusion"): lambda: importlib.import_module(
        ".families.source_retraction.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_retraction", "rank"): lambda: importlib.import_module(
        ".families.source_retraction.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_retraction", "context"): lambda: importlib.import_module(
        ".families.source_retraction.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_retraction", "plan"): lambda: importlib.import_module(
        ".families.source_retraction.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_retraction", "resource"): lambda: importlib.import_module(
        ".families.source_retraction.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_retraction", "schedule"): lambda: importlib.import_module(
        ".families.source_retraction.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_retraction", "permission"): lambda: importlib.import_module(
        ".families.source_retraction.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_retraction", "native"): lambda: importlib.import_module(
        ".families.source_retraction.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_retraction", "replay"): lambda: importlib.import_module(
        ".families.source_retraction.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_retraction", "memory"): lambda: importlib.import_module(
        ".families.source_retraction.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_retraction", "privacy"): lambda: importlib.import_module(
        ".families.source_retraction.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_retraction", "evaluate"): lambda: importlib.import_module(
        ".families.source_retraction.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_retraction", "audit"): lambda: importlib.import_module(
        ".families.source_retraction.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_retraction", "recover"): lambda: importlib.import_module(
        ".families.source_retraction.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_retraction", "stream"): lambda: importlib.import_module(
        ".families.source_retraction.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_retraction", "tool"): lambda: importlib.import_module(
        ".families.source_retraction.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_retraction", "checkpoint"): lambda: importlib.import_module(
        ".families.source_retraction.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_retraction", "health"): lambda: importlib.import_module(
        ".families.source_retraction.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("expiry_enforcement", "source"): lambda: importlib.import_module(
        ".families.expiry_enforcement.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("expiry_enforcement", "search"): lambda: importlib.import_module(
        ".families.expiry_enforcement.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("expiry_enforcement", "fusion"): lambda: importlib.import_module(
        ".families.expiry_enforcement.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("expiry_enforcement", "rank"): lambda: importlib.import_module(
        ".families.expiry_enforcement.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("expiry_enforcement", "context"): lambda: importlib.import_module(
        ".families.expiry_enforcement.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("expiry_enforcement", "plan"): lambda: importlib.import_module(
        ".families.expiry_enforcement.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("expiry_enforcement", "resource"): lambda: importlib.import_module(
        ".families.expiry_enforcement.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("expiry_enforcement", "schedule"): lambda: importlib.import_module(
        ".families.expiry_enforcement.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("expiry_enforcement", "permission"): lambda: importlib.import_module(
        ".families.expiry_enforcement.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("expiry_enforcement", "native"): lambda: importlib.import_module(
        ".families.expiry_enforcement.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("expiry_enforcement", "replay"): lambda: importlib.import_module(
        ".families.expiry_enforcement.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("expiry_enforcement", "memory"): lambda: importlib.import_module(
        ".families.expiry_enforcement.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("expiry_enforcement", "privacy"): lambda: importlib.import_module(
        ".families.expiry_enforcement.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("expiry_enforcement", "evaluate"): lambda: importlib.import_module(
        ".families.expiry_enforcement.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("expiry_enforcement", "audit"): lambda: importlib.import_module(
        ".families.expiry_enforcement.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("expiry_enforcement", "recover"): lambda: importlib.import_module(
        ".families.expiry_enforcement.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("expiry_enforcement", "stream"): lambda: importlib.import_module(
        ".families.expiry_enforcement.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("expiry_enforcement", "tool"): lambda: importlib.import_module(
        ".families.expiry_enforcement.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("expiry_enforcement", "checkpoint"): lambda: importlib.import_module(
        ".families.expiry_enforcement.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("expiry_enforcement", "health"): lambda: importlib.import_module(
        ".families.expiry_enforcement.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tenant_compartment", "source"): lambda: importlib.import_module(
        ".families.tenant_compartment.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tenant_compartment", "search"): lambda: importlib.import_module(
        ".families.tenant_compartment.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tenant_compartment", "fusion"): lambda: importlib.import_module(
        ".families.tenant_compartment.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tenant_compartment", "rank"): lambda: importlib.import_module(
        ".families.tenant_compartment.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tenant_compartment", "context"): lambda: importlib.import_module(
        ".families.tenant_compartment.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tenant_compartment", "plan"): lambda: importlib.import_module(
        ".families.tenant_compartment.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tenant_compartment", "resource"): lambda: importlib.import_module(
        ".families.tenant_compartment.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tenant_compartment", "schedule"): lambda: importlib.import_module(
        ".families.tenant_compartment.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tenant_compartment", "permission"): lambda: importlib.import_module(
        ".families.tenant_compartment.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tenant_compartment", "native"): lambda: importlib.import_module(
        ".families.tenant_compartment.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tenant_compartment", "replay"): lambda: importlib.import_module(
        ".families.tenant_compartment.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tenant_compartment", "memory"): lambda: importlib.import_module(
        ".families.tenant_compartment.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tenant_compartment", "privacy"): lambda: importlib.import_module(
        ".families.tenant_compartment.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tenant_compartment", "evaluate"): lambda: importlib.import_module(
        ".families.tenant_compartment.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tenant_compartment", "audit"): lambda: importlib.import_module(
        ".families.tenant_compartment.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tenant_compartment", "recover"): lambda: importlib.import_module(
        ".families.tenant_compartment.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tenant_compartment", "stream"): lambda: importlib.import_module(
        ".families.tenant_compartment.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tenant_compartment", "tool"): lambda: importlib.import_module(
        ".families.tenant_compartment.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tenant_compartment", "checkpoint"): lambda: importlib.import_module(
        ".families.tenant_compartment.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tenant_compartment", "health"): lambda: importlib.import_module(
        ".families.tenant_compartment.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("snapshot_plan", "source"): lambda: importlib.import_module(
        ".families.snapshot_plan.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("snapshot_plan", "search"): lambda: importlib.import_module(
        ".families.snapshot_plan.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("snapshot_plan", "fusion"): lambda: importlib.import_module(
        ".families.snapshot_plan.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("snapshot_plan", "rank"): lambda: importlib.import_module(
        ".families.snapshot_plan.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("snapshot_plan", "context"): lambda: importlib.import_module(
        ".families.snapshot_plan.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("snapshot_plan", "plan"): lambda: importlib.import_module(
        ".families.snapshot_plan.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("snapshot_plan", "resource"): lambda: importlib.import_module(
        ".families.snapshot_plan.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("snapshot_plan", "schedule"): lambda: importlib.import_module(
        ".families.snapshot_plan.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("snapshot_plan", "permission"): lambda: importlib.import_module(
        ".families.snapshot_plan.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("snapshot_plan", "native"): lambda: importlib.import_module(
        ".families.snapshot_plan.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("snapshot_plan", "replay"): lambda: importlib.import_module(
        ".families.snapshot_plan.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("snapshot_plan", "memory"): lambda: importlib.import_module(
        ".families.snapshot_plan.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("snapshot_plan", "privacy"): lambda: importlib.import_module(
        ".families.snapshot_plan.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("snapshot_plan", "evaluate"): lambda: importlib.import_module(
        ".families.snapshot_plan.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("snapshot_plan", "audit"): lambda: importlib.import_module(
        ".families.snapshot_plan.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("snapshot_plan", "recover"): lambda: importlib.import_module(
        ".families.snapshot_plan.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("snapshot_plan", "stream"): lambda: importlib.import_module(
        ".families.snapshot_plan.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("snapshot_plan", "tool"): lambda: importlib.import_module(
        ".families.snapshot_plan.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("snapshot_plan", "checkpoint"): lambda: importlib.import_module(
        ".families.snapshot_plan.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("snapshot_plan", "health"): lambda: importlib.import_module(
        ".families.snapshot_plan.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_dedup", "source"): lambda: importlib.import_module(
        ".families.memory_dedup.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_dedup", "search"): lambda: importlib.import_module(
        ".families.memory_dedup.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_dedup", "fusion"): lambda: importlib.import_module(
        ".families.memory_dedup.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_dedup", "rank"): lambda: importlib.import_module(
        ".families.memory_dedup.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_dedup", "context"): lambda: importlib.import_module(
        ".families.memory_dedup.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_dedup", "plan"): lambda: importlib.import_module(
        ".families.memory_dedup.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_dedup", "resource"): lambda: importlib.import_module(
        ".families.memory_dedup.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_dedup", "schedule"): lambda: importlib.import_module(
        ".families.memory_dedup.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_dedup", "permission"): lambda: importlib.import_module(
        ".families.memory_dedup.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_dedup", "native"): lambda: importlib.import_module(
        ".families.memory_dedup.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_dedup", "replay"): lambda: importlib.import_module(
        ".families.memory_dedup.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_dedup", "memory"): lambda: importlib.import_module(
        ".families.memory_dedup.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_dedup", "privacy"): lambda: importlib.import_module(
        ".families.memory_dedup.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_dedup", "evaluate"): lambda: importlib.import_module(
        ".families.memory_dedup.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_dedup", "audit"): lambda: importlib.import_module(
        ".families.memory_dedup.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_dedup", "recover"): lambda: importlib.import_module(
        ".families.memory_dedup.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_dedup", "stream"): lambda: importlib.import_module(
        ".families.memory_dedup.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_dedup", "tool"): lambda: importlib.import_module(
        ".families.memory_dedup.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_dedup", "checkpoint"): lambda: importlib.import_module(
        ".families.memory_dedup.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_dedup", "health"): lambda: importlib.import_module(
        ".families.memory_dedup.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("provenance_refresh", "source"): lambda: importlib.import_module(
        ".families.provenance_refresh.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("provenance_refresh", "search"): lambda: importlib.import_module(
        ".families.provenance_refresh.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("provenance_refresh", "fusion"): lambda: importlib.import_module(
        ".families.provenance_refresh.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("provenance_refresh", "rank"): lambda: importlib.import_module(
        ".families.provenance_refresh.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("provenance_refresh", "context"): lambda: importlib.import_module(
        ".families.provenance_refresh.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("provenance_refresh", "plan"): lambda: importlib.import_module(
        ".families.provenance_refresh.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("provenance_refresh", "resource"): lambda: importlib.import_module(
        ".families.provenance_refresh.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("provenance_refresh", "schedule"): lambda: importlib.import_module(
        ".families.provenance_refresh.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("provenance_refresh", "permission"): lambda: importlib.import_module(
        ".families.provenance_refresh.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("provenance_refresh", "native"): lambda: importlib.import_module(
        ".families.provenance_refresh.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("provenance_refresh", "replay"): lambda: importlib.import_module(
        ".families.provenance_refresh.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("provenance_refresh", "memory"): lambda: importlib.import_module(
        ".families.provenance_refresh.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("provenance_refresh", "privacy"): lambda: importlib.import_module(
        ".families.provenance_refresh.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("provenance_refresh", "evaluate"): lambda: importlib.import_module(
        ".families.provenance_refresh.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("provenance_refresh", "audit"): lambda: importlib.import_module(
        ".families.provenance_refresh.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("provenance_refresh", "recover"): lambda: importlib.import_module(
        ".families.provenance_refresh.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("provenance_refresh", "stream"): lambda: importlib.import_module(
        ".families.provenance_refresh.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("provenance_refresh", "tool"): lambda: importlib.import_module(
        ".families.provenance_refresh.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("provenance_refresh", "checkpoint"): lambda: importlib.import_module(
        ".families.provenance_refresh.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("provenance_refresh", "health"): lambda: importlib.import_module(
        ".families.provenance_refresh.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("lexical_search", "source"): lambda: importlib.import_module(
        ".families.lexical_search.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("lexical_search", "search"): lambda: importlib.import_module(
        ".families.lexical_search.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("lexical_search", "fusion"): lambda: importlib.import_module(
        ".families.lexical_search.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("lexical_search", "rank"): lambda: importlib.import_module(
        ".families.lexical_search.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("lexical_search", "context"): lambda: importlib.import_module(
        ".families.lexical_search.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("lexical_search", "plan"): lambda: importlib.import_module(
        ".families.lexical_search.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("lexical_search", "resource"): lambda: importlib.import_module(
        ".families.lexical_search.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("lexical_search", "schedule"): lambda: importlib.import_module(
        ".families.lexical_search.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("lexical_search", "permission"): lambda: importlib.import_module(
        ".families.lexical_search.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("lexical_search", "native"): lambda: importlib.import_module(
        ".families.lexical_search.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("lexical_search", "replay"): lambda: importlib.import_module(
        ".families.lexical_search.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("lexical_search", "memory"): lambda: importlib.import_module(
        ".families.lexical_search.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("lexical_search", "privacy"): lambda: importlib.import_module(
        ".families.lexical_search.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("lexical_search", "evaluate"): lambda: importlib.import_module(
        ".families.lexical_search.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("lexical_search", "audit"): lambda: importlib.import_module(
        ".families.lexical_search.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("lexical_search", "recover"): lambda: importlib.import_module(
        ".families.lexical_search.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("lexical_search", "stream"): lambda: importlib.import_module(
        ".families.lexical_search.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("lexical_search", "tool"): lambda: importlib.import_module(
        ".families.lexical_search.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("lexical_search", "checkpoint"): lambda: importlib.import_module(
        ".families.lexical_search.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("lexical_search", "health"): lambda: importlib.import_module(
        ".families.lexical_search.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("embedding_search", "source"): lambda: importlib.import_module(
        ".families.embedding_search.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("embedding_search", "search"): lambda: importlib.import_module(
        ".families.embedding_search.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("embedding_search", "fusion"): lambda: importlib.import_module(
        ".families.embedding_search.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("embedding_search", "rank"): lambda: importlib.import_module(
        ".families.embedding_search.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("embedding_search", "context"): lambda: importlib.import_module(
        ".families.embedding_search.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("embedding_search", "plan"): lambda: importlib.import_module(
        ".families.embedding_search.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("embedding_search", "resource"): lambda: importlib.import_module(
        ".families.embedding_search.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("embedding_search", "schedule"): lambda: importlib.import_module(
        ".families.embedding_search.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("embedding_search", "permission"): lambda: importlib.import_module(
        ".families.embedding_search.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("embedding_search", "native"): lambda: importlib.import_module(
        ".families.embedding_search.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("embedding_search", "replay"): lambda: importlib.import_module(
        ".families.embedding_search.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("embedding_search", "memory"): lambda: importlib.import_module(
        ".families.embedding_search.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("embedding_search", "privacy"): lambda: importlib.import_module(
        ".families.embedding_search.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("embedding_search", "evaluate"): lambda: importlib.import_module(
        ".families.embedding_search.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("embedding_search", "audit"): lambda: importlib.import_module(
        ".families.embedding_search.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("embedding_search", "recover"): lambda: importlib.import_module(
        ".families.embedding_search.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("embedding_search", "stream"): lambda: importlib.import_module(
        ".families.embedding_search.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("embedding_search", "tool"): lambda: importlib.import_module(
        ".families.embedding_search.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("embedding_search", "checkpoint"): lambda: importlib.import_module(
        ".families.embedding_search.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("embedding_search", "health"): lambda: importlib.import_module(
        ".families.embedding_search.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hybrid_fusion", "source"): lambda: importlib.import_module(
        ".families.hybrid_fusion.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hybrid_fusion", "search"): lambda: importlib.import_module(
        ".families.hybrid_fusion.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hybrid_fusion", "fusion"): lambda: importlib.import_module(
        ".families.hybrid_fusion.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hybrid_fusion", "rank"): lambda: importlib.import_module(
        ".families.hybrid_fusion.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hybrid_fusion", "context"): lambda: importlib.import_module(
        ".families.hybrid_fusion.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hybrid_fusion", "plan"): lambda: importlib.import_module(
        ".families.hybrid_fusion.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hybrid_fusion", "resource"): lambda: importlib.import_module(
        ".families.hybrid_fusion.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hybrid_fusion", "schedule"): lambda: importlib.import_module(
        ".families.hybrid_fusion.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hybrid_fusion", "permission"): lambda: importlib.import_module(
        ".families.hybrid_fusion.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hybrid_fusion", "native"): lambda: importlib.import_module(
        ".families.hybrid_fusion.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hybrid_fusion", "replay"): lambda: importlib.import_module(
        ".families.hybrid_fusion.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hybrid_fusion", "memory"): lambda: importlib.import_module(
        ".families.hybrid_fusion.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hybrid_fusion", "privacy"): lambda: importlib.import_module(
        ".families.hybrid_fusion.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hybrid_fusion", "evaluate"): lambda: importlib.import_module(
        ".families.hybrid_fusion.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hybrid_fusion", "audit"): lambda: importlib.import_module(
        ".families.hybrid_fusion.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hybrid_fusion", "recover"): lambda: importlib.import_module(
        ".families.hybrid_fusion.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hybrid_fusion", "stream"): lambda: importlib.import_module(
        ".families.hybrid_fusion.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hybrid_fusion", "tool"): lambda: importlib.import_module(
        ".families.hybrid_fusion.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hybrid_fusion", "checkpoint"): lambda: importlib.import_module(
        ".families.hybrid_fusion.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hybrid_fusion", "health"): lambda: importlib.import_module(
        ".families.hybrid_fusion.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("passage_rerank", "source"): lambda: importlib.import_module(
        ".families.passage_rerank.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("passage_rerank", "search"): lambda: importlib.import_module(
        ".families.passage_rerank.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("passage_rerank", "fusion"): lambda: importlib.import_module(
        ".families.passage_rerank.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("passage_rerank", "rank"): lambda: importlib.import_module(
        ".families.passage_rerank.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("passage_rerank", "context"): lambda: importlib.import_module(
        ".families.passage_rerank.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("passage_rerank", "plan"): lambda: importlib.import_module(
        ".families.passage_rerank.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("passage_rerank", "resource"): lambda: importlib.import_module(
        ".families.passage_rerank.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("passage_rerank", "schedule"): lambda: importlib.import_module(
        ".families.passage_rerank.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("passage_rerank", "permission"): lambda: importlib.import_module(
        ".families.passage_rerank.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("passage_rerank", "native"): lambda: importlib.import_module(
        ".families.passage_rerank.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("passage_rerank", "replay"): lambda: importlib.import_module(
        ".families.passage_rerank.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("passage_rerank", "memory"): lambda: importlib.import_module(
        ".families.passage_rerank.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("passage_rerank", "privacy"): lambda: importlib.import_module(
        ".families.passage_rerank.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("passage_rerank", "evaluate"): lambda: importlib.import_module(
        ".families.passage_rerank.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("passage_rerank", "audit"): lambda: importlib.import_module(
        ".families.passage_rerank.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("passage_rerank", "recover"): lambda: importlib.import_module(
        ".families.passage_rerank.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("passage_rerank", "stream"): lambda: importlib.import_module(
        ".families.passage_rerank.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("passage_rerank", "tool"): lambda: importlib.import_module(
        ".families.passage_rerank.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("passage_rerank", "checkpoint"): lambda: importlib.import_module(
        ".families.passage_rerank.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("passage_rerank", "health"): lambda: importlib.import_module(
        ".families.passage_rerank.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_attribution", "source"): lambda: importlib.import_module(
        ".families.source_attribution.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_attribution", "search"): lambda: importlib.import_module(
        ".families.source_attribution.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_attribution", "fusion"): lambda: importlib.import_module(
        ".families.source_attribution.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_attribution", "rank"): lambda: importlib.import_module(
        ".families.source_attribution.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_attribution", "context"): lambda: importlib.import_module(
        ".families.source_attribution.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_attribution", "plan"): lambda: importlib.import_module(
        ".families.source_attribution.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_attribution", "resource"): lambda: importlib.import_module(
        ".families.source_attribution.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_attribution", "schedule"): lambda: importlib.import_module(
        ".families.source_attribution.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_attribution", "permission"): lambda: importlib.import_module(
        ".families.source_attribution.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_attribution", "native"): lambda: importlib.import_module(
        ".families.source_attribution.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_attribution", "replay"): lambda: importlib.import_module(
        ".families.source_attribution.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_attribution", "memory"): lambda: importlib.import_module(
        ".families.source_attribution.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_attribution", "privacy"): lambda: importlib.import_module(
        ".families.source_attribution.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_attribution", "evaluate"): lambda: importlib.import_module(
        ".families.source_attribution.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_attribution", "audit"): lambda: importlib.import_module(
        ".families.source_attribution.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_attribution", "recover"): lambda: importlib.import_module(
        ".families.source_attribution.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_attribution", "stream"): lambda: importlib.import_module(
        ".families.source_attribution.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_attribution", "tool"): lambda: importlib.import_module(
        ".families.source_attribution.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_attribution", "checkpoint"): lambda: importlib.import_module(
        ".families.source_attribution.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_attribution", "health"): lambda: importlib.import_module(
        ".families.source_attribution.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("citation_proof", "source"): lambda: importlib.import_module(
        ".families.citation_proof.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("citation_proof", "search"): lambda: importlib.import_module(
        ".families.citation_proof.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("citation_proof", "fusion"): lambda: importlib.import_module(
        ".families.citation_proof.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("citation_proof", "rank"): lambda: importlib.import_module(
        ".families.citation_proof.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("citation_proof", "context"): lambda: importlib.import_module(
        ".families.citation_proof.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("citation_proof", "plan"): lambda: importlib.import_module(
        ".families.citation_proof.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("citation_proof", "resource"): lambda: importlib.import_module(
        ".families.citation_proof.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("citation_proof", "schedule"): lambda: importlib.import_module(
        ".families.citation_proof.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("citation_proof", "permission"): lambda: importlib.import_module(
        ".families.citation_proof.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("citation_proof", "native"): lambda: importlib.import_module(
        ".families.citation_proof.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("citation_proof", "replay"): lambda: importlib.import_module(
        ".families.citation_proof.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("citation_proof", "memory"): lambda: importlib.import_module(
        ".families.citation_proof.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("citation_proof", "privacy"): lambda: importlib.import_module(
        ".families.citation_proof.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("citation_proof", "evaluate"): lambda: importlib.import_module(
        ".families.citation_proof.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("citation_proof", "audit"): lambda: importlib.import_module(
        ".families.citation_proof.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("citation_proof", "recover"): lambda: importlib.import_module(
        ".families.citation_proof.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("citation_proof", "stream"): lambda: importlib.import_module(
        ".families.citation_proof.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("citation_proof", "tool"): lambda: importlib.import_module(
        ".families.citation_proof.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("citation_proof", "checkpoint"): lambda: importlib.import_module(
        ".families.citation_proof.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("citation_proof", "health"): lambda: importlib.import_module(
        ".families.citation_proof.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("chunk_partition", "source"): lambda: importlib.import_module(
        ".families.chunk_partition.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("chunk_partition", "search"): lambda: importlib.import_module(
        ".families.chunk_partition.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("chunk_partition", "fusion"): lambda: importlib.import_module(
        ".families.chunk_partition.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("chunk_partition", "rank"): lambda: importlib.import_module(
        ".families.chunk_partition.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("chunk_partition", "context"): lambda: importlib.import_module(
        ".families.chunk_partition.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("chunk_partition", "plan"): lambda: importlib.import_module(
        ".families.chunk_partition.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("chunk_partition", "resource"): lambda: importlib.import_module(
        ".families.chunk_partition.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("chunk_partition", "schedule"): lambda: importlib.import_module(
        ".families.chunk_partition.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("chunk_partition", "permission"): lambda: importlib.import_module(
        ".families.chunk_partition.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("chunk_partition", "native"): lambda: importlib.import_module(
        ".families.chunk_partition.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("chunk_partition", "replay"): lambda: importlib.import_module(
        ".families.chunk_partition.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("chunk_partition", "memory"): lambda: importlib.import_module(
        ".families.chunk_partition.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("chunk_partition", "privacy"): lambda: importlib.import_module(
        ".families.chunk_partition.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("chunk_partition", "evaluate"): lambda: importlib.import_module(
        ".families.chunk_partition.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("chunk_partition", "audit"): lambda: importlib.import_module(
        ".families.chunk_partition.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("chunk_partition", "recover"): lambda: importlib.import_module(
        ".families.chunk_partition.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("chunk_partition", "stream"): lambda: importlib.import_module(
        ".families.chunk_partition.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("chunk_partition", "tool"): lambda: importlib.import_module(
        ".families.chunk_partition.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("chunk_partition", "checkpoint"): lambda: importlib.import_module(
        ".families.chunk_partition.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("chunk_partition", "health"): lambda: importlib.import_module(
        ".families.chunk_partition.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("duplicate_filter", "source"): lambda: importlib.import_module(
        ".families.duplicate_filter.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("duplicate_filter", "search"): lambda: importlib.import_module(
        ".families.duplicate_filter.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("duplicate_filter", "fusion"): lambda: importlib.import_module(
        ".families.duplicate_filter.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("duplicate_filter", "rank"): lambda: importlib.import_module(
        ".families.duplicate_filter.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("duplicate_filter", "context"): lambda: importlib.import_module(
        ".families.duplicate_filter.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("duplicate_filter", "plan"): lambda: importlib.import_module(
        ".families.duplicate_filter.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("duplicate_filter", "resource"): lambda: importlib.import_module(
        ".families.duplicate_filter.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("duplicate_filter", "schedule"): lambda: importlib.import_module(
        ".families.duplicate_filter.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("duplicate_filter", "permission"): lambda: importlib.import_module(
        ".families.duplicate_filter.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("duplicate_filter", "native"): lambda: importlib.import_module(
        ".families.duplicate_filter.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("duplicate_filter", "replay"): lambda: importlib.import_module(
        ".families.duplicate_filter.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("duplicate_filter", "memory"): lambda: importlib.import_module(
        ".families.duplicate_filter.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("duplicate_filter", "privacy"): lambda: importlib.import_module(
        ".families.duplicate_filter.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("duplicate_filter", "evaluate"): lambda: importlib.import_module(
        ".families.duplicate_filter.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("duplicate_filter", "audit"): lambda: importlib.import_module(
        ".families.duplicate_filter.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("duplicate_filter", "recover"): lambda: importlib.import_module(
        ".families.duplicate_filter.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("duplicate_filter", "stream"): lambda: importlib.import_module(
        ".families.duplicate_filter.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("duplicate_filter", "tool"): lambda: importlib.import_module(
        ".families.duplicate_filter.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("duplicate_filter", "checkpoint"): lambda: importlib.import_module(
        ".families.duplicate_filter.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("duplicate_filter", "health"): lambda: importlib.import_module(
        ".families.duplicate_filter.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("task_decompose", "source"): lambda: importlib.import_module(
        ".families.task_decompose.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("task_decompose", "search"): lambda: importlib.import_module(
        ".families.task_decompose.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("task_decompose", "fusion"): lambda: importlib.import_module(
        ".families.task_decompose.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("task_decompose", "rank"): lambda: importlib.import_module(
        ".families.task_decompose.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("task_decompose", "context"): lambda: importlib.import_module(
        ".families.task_decompose.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("task_decompose", "plan"): lambda: importlib.import_module(
        ".families.task_decompose.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("task_decompose", "resource"): lambda: importlib.import_module(
        ".families.task_decompose.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("task_decompose", "schedule"): lambda: importlib.import_module(
        ".families.task_decompose.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("task_decompose", "permission"): lambda: importlib.import_module(
        ".families.task_decompose.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("task_decompose", "native"): lambda: importlib.import_module(
        ".families.task_decompose.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("task_decompose", "replay"): lambda: importlib.import_module(
        ".families.task_decompose.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("task_decompose", "memory"): lambda: importlib.import_module(
        ".families.task_decompose.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("task_decompose", "privacy"): lambda: importlib.import_module(
        ".families.task_decompose.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("task_decompose", "evaluate"): lambda: importlib.import_module(
        ".families.task_decompose.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("task_decompose", "audit"): lambda: importlib.import_module(
        ".families.task_decompose.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("task_decompose", "recover"): lambda: importlib.import_module(
        ".families.task_decompose.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("task_decompose", "stream"): lambda: importlib.import_module(
        ".families.task_decompose.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("task_decompose", "tool"): lambda: importlib.import_module(
        ".families.task_decompose.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("task_decompose", "checkpoint"): lambda: importlib.import_module(
        ".families.task_decompose.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("task_decompose", "health"): lambda: importlib.import_module(
        ".families.task_decompose.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("dependency_plan", "source"): lambda: importlib.import_module(
        ".families.dependency_plan.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("dependency_plan", "search"): lambda: importlib.import_module(
        ".families.dependency_plan.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("dependency_plan", "fusion"): lambda: importlib.import_module(
        ".families.dependency_plan.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("dependency_plan", "rank"): lambda: importlib.import_module(
        ".families.dependency_plan.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("dependency_plan", "context"): lambda: importlib.import_module(
        ".families.dependency_plan.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("dependency_plan", "plan"): lambda: importlib.import_module(
        ".families.dependency_plan.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("dependency_plan", "resource"): lambda: importlib.import_module(
        ".families.dependency_plan.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("dependency_plan", "schedule"): lambda: importlib.import_module(
        ".families.dependency_plan.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("dependency_plan", "permission"): lambda: importlib.import_module(
        ".families.dependency_plan.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("dependency_plan", "native"): lambda: importlib.import_module(
        ".families.dependency_plan.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("dependency_plan", "replay"): lambda: importlib.import_module(
        ".families.dependency_plan.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("dependency_plan", "memory"): lambda: importlib.import_module(
        ".families.dependency_plan.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("dependency_plan", "privacy"): lambda: importlib.import_module(
        ".families.dependency_plan.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("dependency_plan", "evaluate"): lambda: importlib.import_module(
        ".families.dependency_plan.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("dependency_plan", "audit"): lambda: importlib.import_module(
        ".families.dependency_plan.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("dependency_plan", "recover"): lambda: importlib.import_module(
        ".families.dependency_plan.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("dependency_plan", "stream"): lambda: importlib.import_module(
        ".families.dependency_plan.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("dependency_plan", "tool"): lambda: importlib.import_module(
        ".families.dependency_plan.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("dependency_plan", "checkpoint"): lambda: importlib.import_module(
        ".families.dependency_plan.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("dependency_plan", "health"): lambda: importlib.import_module(
        ".families.dependency_plan.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_proposal", "source"): lambda: importlib.import_module(
        ".families.tool_proposal.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_proposal", "search"): lambda: importlib.import_module(
        ".families.tool_proposal.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_proposal", "fusion"): lambda: importlib.import_module(
        ".families.tool_proposal.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_proposal", "rank"): lambda: importlib.import_module(
        ".families.tool_proposal.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_proposal", "context"): lambda: importlib.import_module(
        ".families.tool_proposal.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_proposal", "plan"): lambda: importlib.import_module(
        ".families.tool_proposal.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_proposal", "resource"): lambda: importlib.import_module(
        ".families.tool_proposal.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_proposal", "schedule"): lambda: importlib.import_module(
        ".families.tool_proposal.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_proposal", "permission"): lambda: importlib.import_module(
        ".families.tool_proposal.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_proposal", "native"): lambda: importlib.import_module(
        ".families.tool_proposal.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_proposal", "replay"): lambda: importlib.import_module(
        ".families.tool_proposal.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_proposal", "memory"): lambda: importlib.import_module(
        ".families.tool_proposal.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_proposal", "privacy"): lambda: importlib.import_module(
        ".families.tool_proposal.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_proposal", "evaluate"): lambda: importlib.import_module(
        ".families.tool_proposal.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_proposal", "audit"): lambda: importlib.import_module(
        ".families.tool_proposal.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_proposal", "recover"): lambda: importlib.import_module(
        ".families.tool_proposal.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_proposal", "stream"): lambda: importlib.import_module(
        ".families.tool_proposal.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_proposal", "tool"): lambda: importlib.import_module(
        ".families.tool_proposal.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_proposal", "checkpoint"): lambda: importlib.import_module(
        ".families.tool_proposal.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_proposal", "health"): lambda: importlib.import_module(
        ".families.tool_proposal.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_result_proof", "source"): lambda: importlib.import_module(
        ".families.tool_result_proof.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_result_proof", "search"): lambda: importlib.import_module(
        ".families.tool_result_proof.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_result_proof", "fusion"): lambda: importlib.import_module(
        ".families.tool_result_proof.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_result_proof", "rank"): lambda: importlib.import_module(
        ".families.tool_result_proof.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_result_proof", "context"): lambda: importlib.import_module(
        ".families.tool_result_proof.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_result_proof", "plan"): lambda: importlib.import_module(
        ".families.tool_result_proof.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_result_proof", "resource"): lambda: importlib.import_module(
        ".families.tool_result_proof.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_result_proof", "schedule"): lambda: importlib.import_module(
        ".families.tool_result_proof.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_result_proof", "permission"): lambda: importlib.import_module(
        ".families.tool_result_proof.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_result_proof", "native"): lambda: importlib.import_module(
        ".families.tool_result_proof.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_result_proof", "replay"): lambda: importlib.import_module(
        ".families.tool_result_proof.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_result_proof", "memory"): lambda: importlib.import_module(
        ".families.tool_result_proof.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_result_proof", "privacy"): lambda: importlib.import_module(
        ".families.tool_result_proof.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_result_proof", "evaluate"): lambda: importlib.import_module(
        ".families.tool_result_proof.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_result_proof", "audit"): lambda: importlib.import_module(
        ".families.tool_result_proof.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_result_proof", "recover"): lambda: importlib.import_module(
        ".families.tool_result_proof.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_result_proof", "stream"): lambda: importlib.import_module(
        ".families.tool_result_proof.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_result_proof", "tool"): lambda: importlib.import_module(
        ".families.tool_result_proof.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_result_proof", "checkpoint"): lambda: importlib.import_module(
        ".families.tool_result_proof.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("tool_result_proof", "health"): lambda: importlib.import_module(
        ".families.tool_result_proof.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("deadline_gate", "source"): lambda: importlib.import_module(
        ".families.deadline_gate.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("deadline_gate", "search"): lambda: importlib.import_module(
        ".families.deadline_gate.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("deadline_gate", "fusion"): lambda: importlib.import_module(
        ".families.deadline_gate.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("deadline_gate", "rank"): lambda: importlib.import_module(
        ".families.deadline_gate.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("deadline_gate", "context"): lambda: importlib.import_module(
        ".families.deadline_gate.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("deadline_gate", "plan"): lambda: importlib.import_module(
        ".families.deadline_gate.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("deadline_gate", "resource"): lambda: importlib.import_module(
        ".families.deadline_gate.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("deadline_gate", "schedule"): lambda: importlib.import_module(
        ".families.deadline_gate.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("deadline_gate", "permission"): lambda: importlib.import_module(
        ".families.deadline_gate.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("deadline_gate", "native"): lambda: importlib.import_module(
        ".families.deadline_gate.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("deadline_gate", "replay"): lambda: importlib.import_module(
        ".families.deadline_gate.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("deadline_gate", "memory"): lambda: importlib.import_module(
        ".families.deadline_gate.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("deadline_gate", "privacy"): lambda: importlib.import_module(
        ".families.deadline_gate.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("deadline_gate", "evaluate"): lambda: importlib.import_module(
        ".families.deadline_gate.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("deadline_gate", "audit"): lambda: importlib.import_module(
        ".families.deadline_gate.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("deadline_gate", "recover"): lambda: importlib.import_module(
        ".families.deadline_gate.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("deadline_gate", "stream"): lambda: importlib.import_module(
        ".families.deadline_gate.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("deadline_gate", "tool"): lambda: importlib.import_module(
        ".families.deadline_gate.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("deadline_gate", "checkpoint"): lambda: importlib.import_module(
        ".families.deadline_gate.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("deadline_gate", "health"): lambda: importlib.import_module(
        ".families.deadline_gate.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retry_classification", "source"): lambda: importlib.import_module(
        ".families.retry_classification.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retry_classification", "search"): lambda: importlib.import_module(
        ".families.retry_classification.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retry_classification", "fusion"): lambda: importlib.import_module(
        ".families.retry_classification.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retry_classification", "rank"): lambda: importlib.import_module(
        ".families.retry_classification.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retry_classification", "context"): lambda: importlib.import_module(
        ".families.retry_classification.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retry_classification", "plan"): lambda: importlib.import_module(
        ".families.retry_classification.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retry_classification", "resource"): lambda: importlib.import_module(
        ".families.retry_classification.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retry_classification", "schedule"): lambda: importlib.import_module(
        ".families.retry_classification.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retry_classification", "permission"): lambda: importlib.import_module(
        ".families.retry_classification.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retry_classification", "native"): lambda: importlib.import_module(
        ".families.retry_classification.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retry_classification", "replay"): lambda: importlib.import_module(
        ".families.retry_classification.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retry_classification", "memory"): lambda: importlib.import_module(
        ".families.retry_classification.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retry_classification", "privacy"): lambda: importlib.import_module(
        ".families.retry_classification.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retry_classification", "evaluate"): lambda: importlib.import_module(
        ".families.retry_classification.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retry_classification", "audit"): lambda: importlib.import_module(
        ".families.retry_classification.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retry_classification", "recover"): lambda: importlib.import_module(
        ".families.retry_classification.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retry_classification", "stream"): lambda: importlib.import_module(
        ".families.retry_classification.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retry_classification", "tool"): lambda: importlib.import_module(
        ".families.retry_classification.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retry_classification", "checkpoint"): lambda: importlib.import_module(
        ".families.retry_classification.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("retry_classification", "health"): lambda: importlib.import_module(
        ".families.retry_classification.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("operator_escalation", "source"): lambda: importlib.import_module(
        ".families.operator_escalation.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("operator_escalation", "search"): lambda: importlib.import_module(
        ".families.operator_escalation.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("operator_escalation", "fusion"): lambda: importlib.import_module(
        ".families.operator_escalation.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("operator_escalation", "rank"): lambda: importlib.import_module(
        ".families.operator_escalation.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("operator_escalation", "context"): lambda: importlib.import_module(
        ".families.operator_escalation.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("operator_escalation", "plan"): lambda: importlib.import_module(
        ".families.operator_escalation.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("operator_escalation", "resource"): lambda: importlib.import_module(
        ".families.operator_escalation.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("operator_escalation", "schedule"): lambda: importlib.import_module(
        ".families.operator_escalation.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("operator_escalation", "permission"): lambda: importlib.import_module(
        ".families.operator_escalation.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("operator_escalation", "native"): lambda: importlib.import_module(
        ".families.operator_escalation.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("operator_escalation", "replay"): lambda: importlib.import_module(
        ".families.operator_escalation.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("operator_escalation", "memory"): lambda: importlib.import_module(
        ".families.operator_escalation.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("operator_escalation", "privacy"): lambda: importlib.import_module(
        ".families.operator_escalation.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("operator_escalation", "evaluate"): lambda: importlib.import_module(
        ".families.operator_escalation.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("operator_escalation", "audit"): lambda: importlib.import_module(
        ".families.operator_escalation.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("operator_escalation", "recover"): lambda: importlib.import_module(
        ".families.operator_escalation.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("operator_escalation", "stream"): lambda: importlib.import_module(
        ".families.operator_escalation.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("operator_escalation", "tool"): lambda: importlib.import_module(
        ".families.operator_escalation.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("operator_escalation", "checkpoint"): lambda: importlib.import_module(
        ".families.operator_escalation.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("operator_escalation", "health"): lambda: importlib.import_module(
        ".families.operator_escalation.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("circuit_recovery", "source"): lambda: importlib.import_module(
        ".families.circuit_recovery.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("circuit_recovery", "search"): lambda: importlib.import_module(
        ".families.circuit_recovery.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("circuit_recovery", "fusion"): lambda: importlib.import_module(
        ".families.circuit_recovery.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("circuit_recovery", "rank"): lambda: importlib.import_module(
        ".families.circuit_recovery.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("circuit_recovery", "context"): lambda: importlib.import_module(
        ".families.circuit_recovery.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("circuit_recovery", "plan"): lambda: importlib.import_module(
        ".families.circuit_recovery.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("circuit_recovery", "resource"): lambda: importlib.import_module(
        ".families.circuit_recovery.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("circuit_recovery", "schedule"): lambda: importlib.import_module(
        ".families.circuit_recovery.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("circuit_recovery", "permission"): lambda: importlib.import_module(
        ".families.circuit_recovery.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("circuit_recovery", "native"): lambda: importlib.import_module(
        ".families.circuit_recovery.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("circuit_recovery", "replay"): lambda: importlib.import_module(
        ".families.circuit_recovery.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("circuit_recovery", "memory"): lambda: importlib.import_module(
        ".families.circuit_recovery.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("circuit_recovery", "privacy"): lambda: importlib.import_module(
        ".families.circuit_recovery.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("circuit_recovery", "evaluate"): lambda: importlib.import_module(
        ".families.circuit_recovery.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("circuit_recovery", "audit"): lambda: importlib.import_module(
        ".families.circuit_recovery.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("circuit_recovery", "recover"): lambda: importlib.import_module(
        ".families.circuit_recovery.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("circuit_recovery", "stream"): lambda: importlib.import_module(
        ".families.circuit_recovery.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("circuit_recovery", "tool"): lambda: importlib.import_module(
        ".families.circuit_recovery.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("circuit_recovery", "checkpoint"): lambda: importlib.import_module(
        ".families.circuit_recovery.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("circuit_recovery", "health"): lambda: importlib.import_module(
        ".families.circuit_recovery.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("capacity_admission", "source"): lambda: importlib.import_module(
        ".families.capacity_admission.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("capacity_admission", "search"): lambda: importlib.import_module(
        ".families.capacity_admission.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("capacity_admission", "fusion"): lambda: importlib.import_module(
        ".families.capacity_admission.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("capacity_admission", "rank"): lambda: importlib.import_module(
        ".families.capacity_admission.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("capacity_admission", "context"): lambda: importlib.import_module(
        ".families.capacity_admission.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("capacity_admission", "plan"): lambda: importlib.import_module(
        ".families.capacity_admission.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("capacity_admission", "resource"): lambda: importlib.import_module(
        ".families.capacity_admission.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("capacity_admission", "schedule"): lambda: importlib.import_module(
        ".families.capacity_admission.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("capacity_admission", "permission"): lambda: importlib.import_module(
        ".families.capacity_admission.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("capacity_admission", "native"): lambda: importlib.import_module(
        ".families.capacity_admission.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("capacity_admission", "replay"): lambda: importlib.import_module(
        ".families.capacity_admission.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("capacity_admission", "memory"): lambda: importlib.import_module(
        ".families.capacity_admission.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("capacity_admission", "privacy"): lambda: importlib.import_module(
        ".families.capacity_admission.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("capacity_admission", "evaluate"): lambda: importlib.import_module(
        ".families.capacity_admission.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("capacity_admission", "audit"): lambda: importlib.import_module(
        ".families.capacity_admission.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("capacity_admission", "recover"): lambda: importlib.import_module(
        ".families.capacity_admission.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("capacity_admission", "stream"): lambda: importlib.import_module(
        ".families.capacity_admission.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("capacity_admission", "tool"): lambda: importlib.import_module(
        ".families.capacity_admission.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("capacity_admission", "checkpoint"): lambda: importlib.import_module(
        ".families.capacity_admission.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("capacity_admission", "health"): lambda: importlib.import_module(
        ".families.capacity_admission.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("fair_queue", "source"): lambda: importlib.import_module(
        ".families.fair_queue.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("fair_queue", "search"): lambda: importlib.import_module(
        ".families.fair_queue.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("fair_queue", "fusion"): lambda: importlib.import_module(
        ".families.fair_queue.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("fair_queue", "rank"): lambda: importlib.import_module(
        ".families.fair_queue.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("fair_queue", "context"): lambda: importlib.import_module(
        ".families.fair_queue.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("fair_queue", "plan"): lambda: importlib.import_module(
        ".families.fair_queue.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("fair_queue", "resource"): lambda: importlib.import_module(
        ".families.fair_queue.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("fair_queue", "schedule"): lambda: importlib.import_module(
        ".families.fair_queue.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("fair_queue", "permission"): lambda: importlib.import_module(
        ".families.fair_queue.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("fair_queue", "native"): lambda: importlib.import_module(
        ".families.fair_queue.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("fair_queue", "replay"): lambda: importlib.import_module(
        ".families.fair_queue.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("fair_queue", "memory"): lambda: importlib.import_module(
        ".families.fair_queue.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("fair_queue", "privacy"): lambda: importlib.import_module(
        ".families.fair_queue.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("fair_queue", "evaluate"): lambda: importlib.import_module(
        ".families.fair_queue.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("fair_queue", "audit"): lambda: importlib.import_module(
        ".families.fair_queue.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("fair_queue", "recover"): lambda: importlib.import_module(
        ".families.fair_queue.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("fair_queue", "stream"): lambda: importlib.import_module(
        ".families.fair_queue.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("fair_queue", "tool"): lambda: importlib.import_module(
        ".families.fair_queue.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("fair_queue", "checkpoint"): lambda: importlib.import_module(
        ".families.fair_queue.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("fair_queue", "health"): lambda: importlib.import_module(
        ".families.fair_queue.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_guard", "source"): lambda: importlib.import_module(
        ".families.memory_guard.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_guard", "search"): lambda: importlib.import_module(
        ".families.memory_guard.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_guard", "fusion"): lambda: importlib.import_module(
        ".families.memory_guard.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_guard", "rank"): lambda: importlib.import_module(
        ".families.memory_guard.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_guard", "context"): lambda: importlib.import_module(
        ".families.memory_guard.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_guard", "plan"): lambda: importlib.import_module(
        ".families.memory_guard.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_guard", "resource"): lambda: importlib.import_module(
        ".families.memory_guard.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_guard", "schedule"): lambda: importlib.import_module(
        ".families.memory_guard.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_guard", "permission"): lambda: importlib.import_module(
        ".families.memory_guard.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_guard", "native"): lambda: importlib.import_module(
        ".families.memory_guard.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_guard", "replay"): lambda: importlib.import_module(
        ".families.memory_guard.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_guard", "memory"): lambda: importlib.import_module(
        ".families.memory_guard.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_guard", "privacy"): lambda: importlib.import_module(
        ".families.memory_guard.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_guard", "evaluate"): lambda: importlib.import_module(
        ".families.memory_guard.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_guard", "audit"): lambda: importlib.import_module(
        ".families.memory_guard.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_guard", "recover"): lambda: importlib.import_module(
        ".families.memory_guard.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_guard", "stream"): lambda: importlib.import_module(
        ".families.memory_guard.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_guard", "tool"): lambda: importlib.import_module(
        ".families.memory_guard.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_guard", "checkpoint"): lambda: importlib.import_module(
        ".families.memory_guard.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("memory_guard", "health"): lambda: importlib.import_module(
        ".families.memory_guard.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("disk_guard", "source"): lambda: importlib.import_module(
        ".families.disk_guard.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("disk_guard", "search"): lambda: importlib.import_module(
        ".families.disk_guard.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("disk_guard", "fusion"): lambda: importlib.import_module(
        ".families.disk_guard.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("disk_guard", "rank"): lambda: importlib.import_module(
        ".families.disk_guard.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("disk_guard", "context"): lambda: importlib.import_module(
        ".families.disk_guard.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("disk_guard", "plan"): lambda: importlib.import_module(
        ".families.disk_guard.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("disk_guard", "resource"): lambda: importlib.import_module(
        ".families.disk_guard.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("disk_guard", "schedule"): lambda: importlib.import_module(
        ".families.disk_guard.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("disk_guard", "permission"): lambda: importlib.import_module(
        ".families.disk_guard.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("disk_guard", "native"): lambda: importlib.import_module(
        ".families.disk_guard.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("disk_guard", "replay"): lambda: importlib.import_module(
        ".families.disk_guard.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("disk_guard", "memory"): lambda: importlib.import_module(
        ".families.disk_guard.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("disk_guard", "privacy"): lambda: importlib.import_module(
        ".families.disk_guard.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("disk_guard", "evaluate"): lambda: importlib.import_module(
        ".families.disk_guard.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("disk_guard", "audit"): lambda: importlib.import_module(
        ".families.disk_guard.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("disk_guard", "recover"): lambda: importlib.import_module(
        ".families.disk_guard.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("disk_guard", "stream"): lambda: importlib.import_module(
        ".families.disk_guard.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("disk_guard", "tool"): lambda: importlib.import_module(
        ".families.disk_guard.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("disk_guard", "checkpoint"): lambda: importlib.import_module(
        ".families.disk_guard.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("disk_guard", "health"): lambda: importlib.import_module(
        ".families.disk_guard.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_quota", "source"): lambda: importlib.import_module(
        ".families.token_quota.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_quota", "search"): lambda: importlib.import_module(
        ".families.token_quota.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_quota", "fusion"): lambda: importlib.import_module(
        ".families.token_quota.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_quota", "rank"): lambda: importlib.import_module(
        ".families.token_quota.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_quota", "context"): lambda: importlib.import_module(
        ".families.token_quota.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_quota", "plan"): lambda: importlib.import_module(
        ".families.token_quota.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_quota", "resource"): lambda: importlib.import_module(
        ".families.token_quota.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_quota", "schedule"): lambda: importlib.import_module(
        ".families.token_quota.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_quota", "permission"): lambda: importlib.import_module(
        ".families.token_quota.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_quota", "native"): lambda: importlib.import_module(
        ".families.token_quota.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_quota", "replay"): lambda: importlib.import_module(
        ".families.token_quota.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_quota", "memory"): lambda: importlib.import_module(
        ".families.token_quota.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_quota", "privacy"): lambda: importlib.import_module(
        ".families.token_quota.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_quota", "evaluate"): lambda: importlib.import_module(
        ".families.token_quota.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_quota", "audit"): lambda: importlib.import_module(
        ".families.token_quota.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_quota", "recover"): lambda: importlib.import_module(
        ".families.token_quota.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_quota", "stream"): lambda: importlib.import_module(
        ".families.token_quota.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_quota", "tool"): lambda: importlib.import_module(
        ".families.token_quota.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_quota", "checkpoint"): lambda: importlib.import_module(
        ".families.token_quota.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("token_quota", "health"): lambda: importlib.import_module(
        ".families.token_quota.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("burst_control", "source"): lambda: importlib.import_module(
        ".families.burst_control.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("burst_control", "search"): lambda: importlib.import_module(
        ".families.burst_control.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("burst_control", "fusion"): lambda: importlib.import_module(
        ".families.burst_control.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("burst_control", "rank"): lambda: importlib.import_module(
        ".families.burst_control.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("burst_control", "context"): lambda: importlib.import_module(
        ".families.burst_control.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("burst_control", "plan"): lambda: importlib.import_module(
        ".families.burst_control.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("burst_control", "resource"): lambda: importlib.import_module(
        ".families.burst_control.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("burst_control", "schedule"): lambda: importlib.import_module(
        ".families.burst_control.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("burst_control", "permission"): lambda: importlib.import_module(
        ".families.burst_control.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("burst_control", "native"): lambda: importlib.import_module(
        ".families.burst_control.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("burst_control", "replay"): lambda: importlib.import_module(
        ".families.burst_control.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("burst_control", "memory"): lambda: importlib.import_module(
        ".families.burst_control.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("burst_control", "privacy"): lambda: importlib.import_module(
        ".families.burst_control.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("burst_control", "evaluate"): lambda: importlib.import_module(
        ".families.burst_control.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("burst_control", "audit"): lambda: importlib.import_module(
        ".families.burst_control.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("burst_control", "recover"): lambda: importlib.import_module(
        ".families.burst_control.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("burst_control", "stream"): lambda: importlib.import_module(
        ".families.burst_control.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("burst_control", "tool"): lambda: importlib.import_module(
        ".families.burst_control.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("burst_control", "checkpoint"): lambda: importlib.import_module(
        ".families.burst_control.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("burst_control", "health"): lambda: importlib.import_module(
        ".families.burst_control.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("preemption_hold", "source"): lambda: importlib.import_module(
        ".families.preemption_hold.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("preemption_hold", "search"): lambda: importlib.import_module(
        ".families.preemption_hold.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("preemption_hold", "fusion"): lambda: importlib.import_module(
        ".families.preemption_hold.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("preemption_hold", "rank"): lambda: importlib.import_module(
        ".families.preemption_hold.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("preemption_hold", "context"): lambda: importlib.import_module(
        ".families.preemption_hold.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("preemption_hold", "plan"): lambda: importlib.import_module(
        ".families.preemption_hold.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("preemption_hold", "resource"): lambda: importlib.import_module(
        ".families.preemption_hold.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("preemption_hold", "schedule"): lambda: importlib.import_module(
        ".families.preemption_hold.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("preemption_hold", "permission"): lambda: importlib.import_module(
        ".families.preemption_hold.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("preemption_hold", "native"): lambda: importlib.import_module(
        ".families.preemption_hold.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("preemption_hold", "replay"): lambda: importlib.import_module(
        ".families.preemption_hold.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("preemption_hold", "memory"): lambda: importlib.import_module(
        ".families.preemption_hold.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("preemption_hold", "privacy"): lambda: importlib.import_module(
        ".families.preemption_hold.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("preemption_hold", "evaluate"): lambda: importlib.import_module(
        ".families.preemption_hold.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("preemption_hold", "audit"): lambda: importlib.import_module(
        ".families.preemption_hold.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("preemption_hold", "recover"): lambda: importlib.import_module(
        ".families.preemption_hold.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("preemption_hold", "stream"): lambda: importlib.import_module(
        ".families.preemption_hold.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("preemption_hold", "tool"): lambda: importlib.import_module(
        ".families.preemption_hold.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("preemption_hold", "checkpoint"): lambda: importlib.import_module(
        ".families.preemption_hold.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("preemption_hold", "health"): lambda: importlib.import_module(
        ".families.preemption_hold.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("budget_reconcile", "source"): lambda: importlib.import_module(
        ".families.budget_reconcile.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("budget_reconcile", "search"): lambda: importlib.import_module(
        ".families.budget_reconcile.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("budget_reconcile", "fusion"): lambda: importlib.import_module(
        ".families.budget_reconcile.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("budget_reconcile", "rank"): lambda: importlib.import_module(
        ".families.budget_reconcile.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("budget_reconcile", "context"): lambda: importlib.import_module(
        ".families.budget_reconcile.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("budget_reconcile", "plan"): lambda: importlib.import_module(
        ".families.budget_reconcile.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("budget_reconcile", "resource"): lambda: importlib.import_module(
        ".families.budget_reconcile.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("budget_reconcile", "schedule"): lambda: importlib.import_module(
        ".families.budget_reconcile.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("budget_reconcile", "permission"): lambda: importlib.import_module(
        ".families.budget_reconcile.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("budget_reconcile", "native"): lambda: importlib.import_module(
        ".families.budget_reconcile.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("budget_reconcile", "replay"): lambda: importlib.import_module(
        ".families.budget_reconcile.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("budget_reconcile", "memory"): lambda: importlib.import_module(
        ".families.budget_reconcile.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("budget_reconcile", "privacy"): lambda: importlib.import_module(
        ".families.budget_reconcile.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("budget_reconcile", "evaluate"): lambda: importlib.import_module(
        ".families.budget_reconcile.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("budget_reconcile", "audit"): lambda: importlib.import_module(
        ".families.budget_reconcile.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("budget_reconcile", "recover"): lambda: importlib.import_module(
        ".families.budget_reconcile.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("budget_reconcile", "stream"): lambda: importlib.import_module(
        ".families.budget_reconcile.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("budget_reconcile", "tool"): lambda: importlib.import_module(
        ".families.budget_reconcile.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("budget_reconcile", "checkpoint"): lambda: importlib.import_module(
        ".families.budget_reconcile.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("budget_reconcile", "health"): lambda: importlib.import_module(
        ".families.budget_reconcile.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("benchmark_admission", "source"): lambda: importlib.import_module(
        ".families.benchmark_admission.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("benchmark_admission", "search"): lambda: importlib.import_module(
        ".families.benchmark_admission.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("benchmark_admission", "fusion"): lambda: importlib.import_module(
        ".families.benchmark_admission.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("benchmark_admission", "rank"): lambda: importlib.import_module(
        ".families.benchmark_admission.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("benchmark_admission", "context"): lambda: importlib.import_module(
        ".families.benchmark_admission.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("benchmark_admission", "plan"): lambda: importlib.import_module(
        ".families.benchmark_admission.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("benchmark_admission", "resource"): lambda: importlib.import_module(
        ".families.benchmark_admission.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("benchmark_admission", "schedule"): lambda: importlib.import_module(
        ".families.benchmark_admission.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("benchmark_admission", "permission"): lambda: importlib.import_module(
        ".families.benchmark_admission.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("benchmark_admission", "native"): lambda: importlib.import_module(
        ".families.benchmark_admission.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("benchmark_admission", "replay"): lambda: importlib.import_module(
        ".families.benchmark_admission.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("benchmark_admission", "memory"): lambda: importlib.import_module(
        ".families.benchmark_admission.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("benchmark_admission", "privacy"): lambda: importlib.import_module(
        ".families.benchmark_admission.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("benchmark_admission", "evaluate"): lambda: importlib.import_module(
        ".families.benchmark_admission.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("benchmark_admission", "audit"): lambda: importlib.import_module(
        ".families.benchmark_admission.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("benchmark_admission", "recover"): lambda: importlib.import_module(
        ".families.benchmark_admission.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("benchmark_admission", "stream"): lambda: importlib.import_module(
        ".families.benchmark_admission.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("benchmark_admission", "tool"): lambda: importlib.import_module(
        ".families.benchmark_admission.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("benchmark_admission", "checkpoint"): lambda: importlib.import_module(
        ".families.benchmark_admission.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("benchmark_admission", "health"): lambda: importlib.import_module(
        ".families.benchmark_admission.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("finite_metrics", "source"): lambda: importlib.import_module(
        ".families.finite_metrics.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("finite_metrics", "search"): lambda: importlib.import_module(
        ".families.finite_metrics.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("finite_metrics", "fusion"): lambda: importlib.import_module(
        ".families.finite_metrics.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("finite_metrics", "rank"): lambda: importlib.import_module(
        ".families.finite_metrics.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("finite_metrics", "context"): lambda: importlib.import_module(
        ".families.finite_metrics.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("finite_metrics", "plan"): lambda: importlib.import_module(
        ".families.finite_metrics.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("finite_metrics", "resource"): lambda: importlib.import_module(
        ".families.finite_metrics.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("finite_metrics", "schedule"): lambda: importlib.import_module(
        ".families.finite_metrics.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("finite_metrics", "permission"): lambda: importlib.import_module(
        ".families.finite_metrics.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("finite_metrics", "native"): lambda: importlib.import_module(
        ".families.finite_metrics.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("finite_metrics", "replay"): lambda: importlib.import_module(
        ".families.finite_metrics.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("finite_metrics", "memory"): lambda: importlib.import_module(
        ".families.finite_metrics.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("finite_metrics", "privacy"): lambda: importlib.import_module(
        ".families.finite_metrics.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("finite_metrics", "evaluate"): lambda: importlib.import_module(
        ".families.finite_metrics.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("finite_metrics", "audit"): lambda: importlib.import_module(
        ".families.finite_metrics.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("finite_metrics", "recover"): lambda: importlib.import_module(
        ".families.finite_metrics.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("finite_metrics", "stream"): lambda: importlib.import_module(
        ".families.finite_metrics.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("finite_metrics", "tool"): lambda: importlib.import_module(
        ".families.finite_metrics.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("finite_metrics", "checkpoint"): lambda: importlib.import_module(
        ".families.finite_metrics.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("finite_metrics", "health"): lambda: importlib.import_module(
        ".families.finite_metrics.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("output_shape", "source"): lambda: importlib.import_module(
        ".families.output_shape.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("output_shape", "search"): lambda: importlib.import_module(
        ".families.output_shape.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("output_shape", "fusion"): lambda: importlib.import_module(
        ".families.output_shape.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("output_shape", "rank"): lambda: importlib.import_module(
        ".families.output_shape.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("output_shape", "context"): lambda: importlib.import_module(
        ".families.output_shape.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("output_shape", "plan"): lambda: importlib.import_module(
        ".families.output_shape.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("output_shape", "resource"): lambda: importlib.import_module(
        ".families.output_shape.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("output_shape", "schedule"): lambda: importlib.import_module(
        ".families.output_shape.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("output_shape", "permission"): lambda: importlib.import_module(
        ".families.output_shape.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("output_shape", "native"): lambda: importlib.import_module(
        ".families.output_shape.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("output_shape", "replay"): lambda: importlib.import_module(
        ".families.output_shape.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("output_shape", "memory"): lambda: importlib.import_module(
        ".families.output_shape.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("output_shape", "privacy"): lambda: importlib.import_module(
        ".families.output_shape.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("output_shape", "evaluate"): lambda: importlib.import_module(
        ".families.output_shape.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("output_shape", "audit"): lambda: importlib.import_module(
        ".families.output_shape.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("output_shape", "recover"): lambda: importlib.import_module(
        ".families.output_shape.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("output_shape", "stream"): lambda: importlib.import_module(
        ".families.output_shape.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("output_shape", "tool"): lambda: importlib.import_module(
        ".families.output_shape.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("output_shape", "checkpoint"): lambda: importlib.import_module(
        ".families.output_shape.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("output_shape", "health"): lambda: importlib.import_module(
        ".families.output_shape.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("refusal_quality", "source"): lambda: importlib.import_module(
        ".families.refusal_quality.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("refusal_quality", "search"): lambda: importlib.import_module(
        ".families.refusal_quality.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("refusal_quality", "fusion"): lambda: importlib.import_module(
        ".families.refusal_quality.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("refusal_quality", "rank"): lambda: importlib.import_module(
        ".families.refusal_quality.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("refusal_quality", "context"): lambda: importlib.import_module(
        ".families.refusal_quality.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("refusal_quality", "plan"): lambda: importlib.import_module(
        ".families.refusal_quality.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("refusal_quality", "resource"): lambda: importlib.import_module(
        ".families.refusal_quality.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("refusal_quality", "schedule"): lambda: importlib.import_module(
        ".families.refusal_quality.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("refusal_quality", "permission"): lambda: importlib.import_module(
        ".families.refusal_quality.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("refusal_quality", "native"): lambda: importlib.import_module(
        ".families.refusal_quality.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("refusal_quality", "replay"): lambda: importlib.import_module(
        ".families.refusal_quality.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("refusal_quality", "memory"): lambda: importlib.import_module(
        ".families.refusal_quality.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("refusal_quality", "privacy"): lambda: importlib.import_module(
        ".families.refusal_quality.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("refusal_quality", "evaluate"): lambda: importlib.import_module(
        ".families.refusal_quality.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("refusal_quality", "audit"): lambda: importlib.import_module(
        ".families.refusal_quality.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("refusal_quality", "recover"): lambda: importlib.import_module(
        ".families.refusal_quality.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("refusal_quality", "stream"): lambda: importlib.import_module(
        ".families.refusal_quality.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("refusal_quality", "tool"): lambda: importlib.import_module(
        ".families.refusal_quality.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("refusal_quality", "checkpoint"): lambda: importlib.import_module(
        ".families.refusal_quality.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("refusal_quality", "health"): lambda: importlib.import_module(
        ".families.refusal_quality.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_quality", "source"): lambda: importlib.import_module(
        ".families.source_quality.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_quality", "search"): lambda: importlib.import_module(
        ".families.source_quality.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_quality", "fusion"): lambda: importlib.import_module(
        ".families.source_quality.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_quality", "rank"): lambda: importlib.import_module(
        ".families.source_quality.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_quality", "context"): lambda: importlib.import_module(
        ".families.source_quality.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_quality", "plan"): lambda: importlib.import_module(
        ".families.source_quality.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_quality", "resource"): lambda: importlib.import_module(
        ".families.source_quality.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_quality", "schedule"): lambda: importlib.import_module(
        ".families.source_quality.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_quality", "permission"): lambda: importlib.import_module(
        ".families.source_quality.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_quality", "native"): lambda: importlib.import_module(
        ".families.source_quality.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_quality", "replay"): lambda: importlib.import_module(
        ".families.source_quality.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_quality", "memory"): lambda: importlib.import_module(
        ".families.source_quality.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_quality", "privacy"): lambda: importlib.import_module(
        ".families.source_quality.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_quality", "evaluate"): lambda: importlib.import_module(
        ".families.source_quality.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_quality", "audit"): lambda: importlib.import_module(
        ".families.source_quality.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_quality", "recover"): lambda: importlib.import_module(
        ".families.source_quality.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_quality", "stream"): lambda: importlib.import_module(
        ".families.source_quality.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_quality", "tool"): lambda: importlib.import_module(
        ".families.source_quality.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_quality", "checkpoint"): lambda: importlib.import_module(
        ".families.source_quality.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("source_quality", "health"): lambda: importlib.import_module(
        ".families.source_quality.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("answer_grounding", "source"): lambda: importlib.import_module(
        ".families.answer_grounding.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("answer_grounding", "search"): lambda: importlib.import_module(
        ".families.answer_grounding.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("answer_grounding", "fusion"): lambda: importlib.import_module(
        ".families.answer_grounding.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("answer_grounding", "rank"): lambda: importlib.import_module(
        ".families.answer_grounding.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("answer_grounding", "context"): lambda: importlib.import_module(
        ".families.answer_grounding.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("answer_grounding", "plan"): lambda: importlib.import_module(
        ".families.answer_grounding.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("answer_grounding", "resource"): lambda: importlib.import_module(
        ".families.answer_grounding.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("answer_grounding", "schedule"): lambda: importlib.import_module(
        ".families.answer_grounding.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("answer_grounding", "permission"): lambda: importlib.import_module(
        ".families.answer_grounding.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("answer_grounding", "native"): lambda: importlib.import_module(
        ".families.answer_grounding.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("answer_grounding", "replay"): lambda: importlib.import_module(
        ".families.answer_grounding.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("answer_grounding", "memory"): lambda: importlib.import_module(
        ".families.answer_grounding.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("answer_grounding", "privacy"): lambda: importlib.import_module(
        ".families.answer_grounding.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("answer_grounding", "evaluate"): lambda: importlib.import_module(
        ".families.answer_grounding.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("answer_grounding", "audit"): lambda: importlib.import_module(
        ".families.answer_grounding.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("answer_grounding", "recover"): lambda: importlib.import_module(
        ".families.answer_grounding.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("answer_grounding", "stream"): lambda: importlib.import_module(
        ".families.answer_grounding.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("answer_grounding", "tool"): lambda: importlib.import_module(
        ".families.answer_grounding.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("answer_grounding", "checkpoint"): lambda: importlib.import_module(
        ".families.answer_grounding.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("answer_grounding", "health"): lambda: importlib.import_module(
        ".families.answer_grounding.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hallucination_hold", "source"): lambda: importlib.import_module(
        ".families.hallucination_hold.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hallucination_hold", "search"): lambda: importlib.import_module(
        ".families.hallucination_hold.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hallucination_hold", "fusion"): lambda: importlib.import_module(
        ".families.hallucination_hold.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hallucination_hold", "rank"): lambda: importlib.import_module(
        ".families.hallucination_hold.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hallucination_hold", "context"): lambda: importlib.import_module(
        ".families.hallucination_hold.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hallucination_hold", "plan"): lambda: importlib.import_module(
        ".families.hallucination_hold.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hallucination_hold", "resource"): lambda: importlib.import_module(
        ".families.hallucination_hold.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hallucination_hold", "schedule"): lambda: importlib.import_module(
        ".families.hallucination_hold.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hallucination_hold", "permission"): lambda: importlib.import_module(
        ".families.hallucination_hold.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hallucination_hold", "native"): lambda: importlib.import_module(
        ".families.hallucination_hold.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hallucination_hold", "replay"): lambda: importlib.import_module(
        ".families.hallucination_hold.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hallucination_hold", "memory"): lambda: importlib.import_module(
        ".families.hallucination_hold.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hallucination_hold", "privacy"): lambda: importlib.import_module(
        ".families.hallucination_hold.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hallucination_hold", "evaluate"): lambda: importlib.import_module(
        ".families.hallucination_hold.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hallucination_hold", "audit"): lambda: importlib.import_module(
        ".families.hallucination_hold.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hallucination_hold", "recover"): lambda: importlib.import_module(
        ".families.hallucination_hold.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hallucination_hold", "stream"): lambda: importlib.import_module(
        ".families.hallucination_hold.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hallucination_hold", "tool"): lambda: importlib.import_module(
        ".families.hallucination_hold.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hallucination_hold", "checkpoint"): lambda: importlib.import_module(
        ".families.hallucination_hold.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hallucination_hold", "health"): lambda: importlib.import_module(
        ".families.hallucination_hold.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("review_ready", "source"): lambda: importlib.import_module(
        ".families.review_ready.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("review_ready", "search"): lambda: importlib.import_module(
        ".families.review_ready.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("review_ready", "fusion"): lambda: importlib.import_module(
        ".families.review_ready.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("review_ready", "rank"): lambda: importlib.import_module(
        ".families.review_ready.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("review_ready", "context"): lambda: importlib.import_module(
        ".families.review_ready.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("review_ready", "plan"): lambda: importlib.import_module(
        ".families.review_ready.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("review_ready", "resource"): lambda: importlib.import_module(
        ".families.review_ready.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("review_ready", "schedule"): lambda: importlib.import_module(
        ".families.review_ready.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("review_ready", "permission"): lambda: importlib.import_module(
        ".families.review_ready.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("review_ready", "native"): lambda: importlib.import_module(
        ".families.review_ready.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("review_ready", "replay"): lambda: importlib.import_module(
        ".families.review_ready.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("review_ready", "memory"): lambda: importlib.import_module(
        ".families.review_ready.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("review_ready", "privacy"): lambda: importlib.import_module(
        ".families.review_ready.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("review_ready", "evaluate"): lambda: importlib.import_module(
        ".families.review_ready.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("review_ready", "audit"): lambda: importlib.import_module(
        ".families.review_ready.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("review_ready", "recover"): lambda: importlib.import_module(
        ".families.review_ready.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("review_ready", "stream"): lambda: importlib.import_module(
        ".families.review_ready.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("review_ready", "tool"): lambda: importlib.import_module(
        ".families.review_ready.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("review_ready", "checkpoint"): lambda: importlib.import_module(
        ".families.review_ready.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("review_ready", "health"): lambda: importlib.import_module(
        ".families.review_ready.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("install_receipt", "source"): lambda: importlib.import_module(
        ".families.install_receipt.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("install_receipt", "search"): lambda: importlib.import_module(
        ".families.install_receipt.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("install_receipt", "fusion"): lambda: importlib.import_module(
        ".families.install_receipt.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("install_receipt", "rank"): lambda: importlib.import_module(
        ".families.install_receipt.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("install_receipt", "context"): lambda: importlib.import_module(
        ".families.install_receipt.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("install_receipt", "plan"): lambda: importlib.import_module(
        ".families.install_receipt.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("install_receipt", "resource"): lambda: importlib.import_module(
        ".families.install_receipt.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("install_receipt", "schedule"): lambda: importlib.import_module(
        ".families.install_receipt.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("install_receipt", "permission"): lambda: importlib.import_module(
        ".families.install_receipt.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("install_receipt", "native"): lambda: importlib.import_module(
        ".families.install_receipt.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("install_receipt", "replay"): lambda: importlib.import_module(
        ".families.install_receipt.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("install_receipt", "memory"): lambda: importlib.import_module(
        ".families.install_receipt.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("install_receipt", "privacy"): lambda: importlib.import_module(
        ".families.install_receipt.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("install_receipt", "evaluate"): lambda: importlib.import_module(
        ".families.install_receipt.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("install_receipt", "audit"): lambda: importlib.import_module(
        ".families.install_receipt.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("install_receipt", "recover"): lambda: importlib.import_module(
        ".families.install_receipt.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("install_receipt", "stream"): lambda: importlib.import_module(
        ".families.install_receipt.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("install_receipt", "tool"): lambda: importlib.import_module(
        ".families.install_receipt.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("install_receipt", "checkpoint"): lambda: importlib.import_module(
        ".families.install_receipt.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("install_receipt", "health"): lambda: importlib.import_module(
        ".families.install_receipt.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("boot_sequence", "source"): lambda: importlib.import_module(
        ".families.boot_sequence.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("boot_sequence", "search"): lambda: importlib.import_module(
        ".families.boot_sequence.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("boot_sequence", "fusion"): lambda: importlib.import_module(
        ".families.boot_sequence.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("boot_sequence", "rank"): lambda: importlib.import_module(
        ".families.boot_sequence.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("boot_sequence", "context"): lambda: importlib.import_module(
        ".families.boot_sequence.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("boot_sequence", "plan"): lambda: importlib.import_module(
        ".families.boot_sequence.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("boot_sequence", "resource"): lambda: importlib.import_module(
        ".families.boot_sequence.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("boot_sequence", "schedule"): lambda: importlib.import_module(
        ".families.boot_sequence.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("boot_sequence", "permission"): lambda: importlib.import_module(
        ".families.boot_sequence.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("boot_sequence", "native"): lambda: importlib.import_module(
        ".families.boot_sequence.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("boot_sequence", "replay"): lambda: importlib.import_module(
        ".families.boot_sequence.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("boot_sequence", "memory"): lambda: importlib.import_module(
        ".families.boot_sequence.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("boot_sequence", "privacy"): lambda: importlib.import_module(
        ".families.boot_sequence.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("boot_sequence", "evaluate"): lambda: importlib.import_module(
        ".families.boot_sequence.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("boot_sequence", "audit"): lambda: importlib.import_module(
        ".families.boot_sequence.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("boot_sequence", "recover"): lambda: importlib.import_module(
        ".families.boot_sequence.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("boot_sequence", "stream"): lambda: importlib.import_module(
        ".families.boot_sequence.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("boot_sequence", "tool"): lambda: importlib.import_module(
        ".families.boot_sequence.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("boot_sequence", "checkpoint"): lambda: importlib.import_module(
        ".families.boot_sequence.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("boot_sequence", "health"): lambda: importlib.import_module(
        ".families.boot_sequence.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("session_scope", "source"): lambda: importlib.import_module(
        ".families.session_scope.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("session_scope", "search"): lambda: importlib.import_module(
        ".families.session_scope.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("session_scope", "fusion"): lambda: importlib.import_module(
        ".families.session_scope.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("session_scope", "rank"): lambda: importlib.import_module(
        ".families.session_scope.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("session_scope", "context"): lambda: importlib.import_module(
        ".families.session_scope.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("session_scope", "plan"): lambda: importlib.import_module(
        ".families.session_scope.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("session_scope", "resource"): lambda: importlib.import_module(
        ".families.session_scope.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("session_scope", "schedule"): lambda: importlib.import_module(
        ".families.session_scope.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("session_scope", "permission"): lambda: importlib.import_module(
        ".families.session_scope.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("session_scope", "native"): lambda: importlib.import_module(
        ".families.session_scope.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("session_scope", "replay"): lambda: importlib.import_module(
        ".families.session_scope.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("session_scope", "memory"): lambda: importlib.import_module(
        ".families.session_scope.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("session_scope", "privacy"): lambda: importlib.import_module(
        ".families.session_scope.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("session_scope", "evaluate"): lambda: importlib.import_module(
        ".families.session_scope.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("session_scope", "audit"): lambda: importlib.import_module(
        ".families.session_scope.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("session_scope", "recover"): lambda: importlib.import_module(
        ".families.session_scope.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("session_scope", "stream"): lambda: importlib.import_module(
        ".families.session_scope.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("session_scope", "tool"): lambda: importlib.import_module(
        ".families.session_scope.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("session_scope", "checkpoint"): lambda: importlib.import_module(
        ".families.session_scope.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("session_scope", "health"): lambda: importlib.import_module(
        ".families.session_scope.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("native_replay", "source"): lambda: importlib.import_module(
        ".families.native_replay.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("native_replay", "search"): lambda: importlib.import_module(
        ".families.native_replay.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("native_replay", "fusion"): lambda: importlib.import_module(
        ".families.native_replay.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("native_replay", "rank"): lambda: importlib.import_module(
        ".families.native_replay.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("native_replay", "context"): lambda: importlib.import_module(
        ".families.native_replay.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("native_replay", "plan"): lambda: importlib.import_module(
        ".families.native_replay.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("native_replay", "resource"): lambda: importlib.import_module(
        ".families.native_replay.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("native_replay", "schedule"): lambda: importlib.import_module(
        ".families.native_replay.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("native_replay", "permission"): lambda: importlib.import_module(
        ".families.native_replay.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("native_replay", "native"): lambda: importlib.import_module(
        ".families.native_replay.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("native_replay", "replay"): lambda: importlib.import_module(
        ".families.native_replay.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("native_replay", "memory"): lambda: importlib.import_module(
        ".families.native_replay.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("native_replay", "privacy"): lambda: importlib.import_module(
        ".families.native_replay.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("native_replay", "evaluate"): lambda: importlib.import_module(
        ".families.native_replay.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("native_replay", "audit"): lambda: importlib.import_module(
        ".families.native_replay.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("native_replay", "recover"): lambda: importlib.import_module(
        ".families.native_replay.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("native_replay", "stream"): lambda: importlib.import_module(
        ".families.native_replay.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("native_replay", "tool"): lambda: importlib.import_module(
        ".families.native_replay.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("native_replay", "checkpoint"): lambda: importlib.import_module(
        ".families.native_replay.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("native_replay", "health"): lambda: importlib.import_module(
        ".families.native_replay.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("outbox_delivery", "source"): lambda: importlib.import_module(
        ".families.outbox_delivery.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("outbox_delivery", "search"): lambda: importlib.import_module(
        ".families.outbox_delivery.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("outbox_delivery", "fusion"): lambda: importlib.import_module(
        ".families.outbox_delivery.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("outbox_delivery", "rank"): lambda: importlib.import_module(
        ".families.outbox_delivery.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("outbox_delivery", "context"): lambda: importlib.import_module(
        ".families.outbox_delivery.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("outbox_delivery", "plan"): lambda: importlib.import_module(
        ".families.outbox_delivery.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("outbox_delivery", "resource"): lambda: importlib.import_module(
        ".families.outbox_delivery.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("outbox_delivery", "schedule"): lambda: importlib.import_module(
        ".families.outbox_delivery.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("outbox_delivery", "permission"): lambda: importlib.import_module(
        ".families.outbox_delivery.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("outbox_delivery", "native"): lambda: importlib.import_module(
        ".families.outbox_delivery.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("outbox_delivery", "replay"): lambda: importlib.import_module(
        ".families.outbox_delivery.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("outbox_delivery", "memory"): lambda: importlib.import_module(
        ".families.outbox_delivery.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("outbox_delivery", "privacy"): lambda: importlib.import_module(
        ".families.outbox_delivery.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("outbox_delivery", "evaluate"): lambda: importlib.import_module(
        ".families.outbox_delivery.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("outbox_delivery", "audit"): lambda: importlib.import_module(
        ".families.outbox_delivery.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("outbox_delivery", "recover"): lambda: importlib.import_module(
        ".families.outbox_delivery.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("outbox_delivery", "stream"): lambda: importlib.import_module(
        ".families.outbox_delivery.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("outbox_delivery", "tool"): lambda: importlib.import_module(
        ".families.outbox_delivery.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("outbox_delivery", "checkpoint"): lambda: importlib.import_module(
        ".families.outbox_delivery.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("outbox_delivery", "health"): lambda: importlib.import_module(
        ".families.outbox_delivery.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hash_journal", "source"): lambda: importlib.import_module(
        ".families.hash_journal.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hash_journal", "search"): lambda: importlib.import_module(
        ".families.hash_journal.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hash_journal", "fusion"): lambda: importlib.import_module(
        ".families.hash_journal.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hash_journal", "rank"): lambda: importlib.import_module(
        ".families.hash_journal.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hash_journal", "context"): lambda: importlib.import_module(
        ".families.hash_journal.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hash_journal", "plan"): lambda: importlib.import_module(
        ".families.hash_journal.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hash_journal", "resource"): lambda: importlib.import_module(
        ".families.hash_journal.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hash_journal", "schedule"): lambda: importlib.import_module(
        ".families.hash_journal.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hash_journal", "permission"): lambda: importlib.import_module(
        ".families.hash_journal.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hash_journal", "native"): lambda: importlib.import_module(
        ".families.hash_journal.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hash_journal", "replay"): lambda: importlib.import_module(
        ".families.hash_journal.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hash_journal", "memory"): lambda: importlib.import_module(
        ".families.hash_journal.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hash_journal", "privacy"): lambda: importlib.import_module(
        ".families.hash_journal.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hash_journal", "evaluate"): lambda: importlib.import_module(
        ".families.hash_journal.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hash_journal", "audit"): lambda: importlib.import_module(
        ".families.hash_journal.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hash_journal", "recover"): lambda: importlib.import_module(
        ".families.hash_journal.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hash_journal", "stream"): lambda: importlib.import_module(
        ".families.hash_journal.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hash_journal", "tool"): lambda: importlib.import_module(
        ".families.hash_journal.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hash_journal", "checkpoint"): lambda: importlib.import_module(
        ".families.hash_journal.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("hash_journal", "health"): lambda: importlib.import_module(
        ".families.hash_journal.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cold_restart", "source"): lambda: importlib.import_module(
        ".families.cold_restart.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cold_restart", "search"): lambda: importlib.import_module(
        ".families.cold_restart.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cold_restart", "fusion"): lambda: importlib.import_module(
        ".families.cold_restart.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cold_restart", "rank"): lambda: importlib.import_module(
        ".families.cold_restart.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cold_restart", "context"): lambda: importlib.import_module(
        ".families.cold_restart.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cold_restart", "plan"): lambda: importlib.import_module(
        ".families.cold_restart.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cold_restart", "resource"): lambda: importlib.import_module(
        ".families.cold_restart.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cold_restart", "schedule"): lambda: importlib.import_module(
        ".families.cold_restart.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cold_restart", "permission"): lambda: importlib.import_module(
        ".families.cold_restart.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cold_restart", "native"): lambda: importlib.import_module(
        ".families.cold_restart.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cold_restart", "replay"): lambda: importlib.import_module(
        ".families.cold_restart.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cold_restart", "memory"): lambda: importlib.import_module(
        ".families.cold_restart.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cold_restart", "privacy"): lambda: importlib.import_module(
        ".families.cold_restart.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cold_restart", "evaluate"): lambda: importlib.import_module(
        ".families.cold_restart.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cold_restart", "audit"): lambda: importlib.import_module(
        ".families.cold_restart.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cold_restart", "recover"): lambda: importlib.import_module(
        ".families.cold_restart.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cold_restart", "stream"): lambda: importlib.import_module(
        ".families.cold_restart.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cold_restart", "tool"): lambda: importlib.import_module(
        ".families.cold_restart.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cold_restart", "checkpoint"): lambda: importlib.import_module(
        ".families.cold_restart.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("cold_restart", "health"): lambda: importlib.import_module(
        ".families.cold_restart.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("release_hold", "source"): lambda: importlib.import_module(
        ".families.release_hold.source",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("release_hold", "search"): lambda: importlib.import_module(
        ".families.release_hold.search",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("release_hold", "fusion"): lambda: importlib.import_module(
        ".families.release_hold.fusion",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("release_hold", "rank"): lambda: importlib.import_module(
        ".families.release_hold.rank",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("release_hold", "context"): lambda: importlib.import_module(
        ".families.release_hold.context",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("release_hold", "plan"): lambda: importlib.import_module(
        ".families.release_hold.plan",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("release_hold", "resource"): lambda: importlib.import_module(
        ".families.release_hold.resource",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("release_hold", "schedule"): lambda: importlib.import_module(
        ".families.release_hold.schedule",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("release_hold", "permission"): lambda: importlib.import_module(
        ".families.release_hold.permission",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("release_hold", "native"): lambda: importlib.import_module(
        ".families.release_hold.native",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("release_hold", "replay"): lambda: importlib.import_module(
        ".families.release_hold.replay",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("release_hold", "memory"): lambda: importlib.import_module(
        ".families.release_hold.memory",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("release_hold", "privacy"): lambda: importlib.import_module(
        ".families.release_hold.privacy",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("release_hold", "evaluate"): lambda: importlib.import_module(
        ".families.release_hold.evaluate",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("release_hold", "audit"): lambda: importlib.import_module(
        ".families.release_hold.audit",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("release_hold", "recover"): lambda: importlib.import_module(
        ".families.release_hold.recover",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("release_hold", "stream"): lambda: importlib.import_module(
        ".families.release_hold.stream",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("release_hold", "tool"): lambda: importlib.import_module(
        ".families.release_hold.tool",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("release_hold", "checkpoint"): lambda: importlib.import_module(
        ".families.release_hold.checkpoint",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
    ("release_hold", "health"): lambda: importlib.import_module(
        ".families.release_hold.health",
        package="skeleton.ai.runtime.operational_ai.offline_cognition",
    ),
})

def _module(family, operation):
    from skeleton.ai.runtime.operational_ai.offline_cognition.catalog import FAMILIES
    if type(family) is not str or family not in FAMILIES:
        raise CognitionError("unregistered capability family")
    if type(operation) is not str:
        raise CognitionError("unknown operational boundary")
    loader = _MODULE_LOADERS.get((family, operation))
    if loader is None:
        raise CognitionError("unknown operational boundary")
    return loader()

def exercise(family,operation,*,attack=False):
    p=read_profile(family)
    if operation not in p.operations:raise CognitionError("unknown operational boundary")
    m=_module(family,operation)
    scope=Scope("local","owner","a"*64,"b"*64)
    if operation=="source":
        raw=b"Actual source text about private offline model retrieval and precise receipts. "*16
        if attack:
            try:m.ingest(raw,source_id="doc",tenant="local",subject="owner",approved=False)
            except CognitionError:return True
            return False
        result=m.ingest(raw,source_id="doc",tenant="local",subject="owner",approved=True)
        return result["source_sha256"]==hash_bytes(raw) and len(m.partition(raw))>=1
    if operation=="search":
        from .retrieval import IndexedDocument
        docs=(IndexedDocument("doc1","local","a"*64,"offline inference and lexical evidence"),
              IndexedDocument("doc2","other","b"*64,"offline inference and lexical evidence"))
        result=m.query(docs,"offline",scope="other" if attack else "local")
        return len(result)==1 and result[0][0]==("doc2" if attack else "doc1")
    if operation=="fusion":
        rows=(("doc1",1.0,"other" if attack else "local"),)
        if attack:
            try:m.combine(rows,rows,scope="local")
            except CognitionError:return True
            return False
        output=m.combine(rows,rows,scope="local")
        return output==("doc1",)
    if operation=="rank":
        from .ranker import RankedSource
        rows=(RankedSource("doc1","local","a"*64,.9,.8,.7,True),
              RankedSource("doc2","local","b"*64,.9,.8,.7,False))
        result=m.score(rows,scope="other" if attack else "local")
        return result==() if attack else len(result)==1 and result[0][0]=="doc1"
    if operation=="context":
        from .contexts import ContextSlice
        rows=(ContextSlice("system","system","a"*64,100,10,True),
              ContextSlice("user","user","b"*64,100,10,True))
        if attack:
            try:m.assemble(rows[:1])
            except CognitionError:return True
            return False
        return set(m.assemble(rows)["selected"])=={"system","user"}
    if operation=="plan":
        from .planner import PlanTask
        a=PlanTask("source",100,0,"retrieval",())
        b=PlanTask("generate",200,128,"model",("source",))
        if attack:
            bad=(PlanTask("a",100,0,"retrieval",("b",)),
                 PlanTask("b",100,0,"retrieval",("a",)))
            try:m.compile(bad)
            except CognitionError:return True
            return False
        result=m.compile((b,a))
        return result["order"]==("source","generate") and result["critical_path_ms"]==300
    if operation=="resource":
        from .budget import Resource
        cap=Resource(512,1000,1000,2)
        need=Resource(128,100,100,1)
        if attack:
            result=m.reserve(Resource(1,100,100,1),(("oversize",need),))
            return result["held"]==("oversize",)
        result=m.reserve(cap,(("task",need),))
        return result["admitted"]==("task",)
    if operation=="schedule":
        from .scheduler import Task
        queue=m.enqueue((Task("task","local",128,1,1000),))
        result=m.admit(queue,now_ns=1000 if attack else 10,tokens=128)
        return result["expired"]==("task",) if attack else result["admitted"]==("task",)
    if operation=="permission":
        from .admission import Permit
        permit=Permit(scope,"c"*64,"read_source",1,100,200,True)
        if attack:
            try:m.inspect(permit,scope,operation="read_source",now_ns=200,source_sha256="c"*64)
            except CognitionError:return True
            return False
        result=m.inspect(permit,scope,operation="read_source",now_ns=150,source_sha256="c"*64)
        return result["permitted"] and not result["external_source_authenticated_by_this_function"]
    if operation=="native":
        from skeleton.testing.laptop_runtime_test_support import FakeWorker
        worker=FakeWorker();worker.spine.create("s_1")
        if attack:
            wrong=Scope("local","owner","c"*64,"b"*64)
            try:m.generate(worker,wrong,"s_1","r1","hello")
            except CognitionError:return worker.generation_calls==0
            return False
        receipt=m.generate(worker,scope,"s_1","r1","hello")
        return receipt.text=="hello" and worker.generation_calls==1
    if operation=="replay":
        from skeleton.testing.laptop_runtime_test_support import FakeWorker
        worker=FakeWorker();worker.spine.create("s_1")
        if attack:
            got=m.read(worker,scope,"s_1","unseen","hello")
            return got is None and worker.generation_calls==0
        worker.turn("s_1","r1","hello")
        receipt=m.read(worker,scope,"s_1","r1","hello")
        return receipt.replayed and worker.generation_calls==1
    if operation=="memory":
        from .memory import MemoryCatalog
        with tempfile.TemporaryDirectory() as temp:
            with MemoryCatalog(temp+"/metadata.sqlite") as catalog:
                m.remember(catalog,scope,"doc","c"*64,length=12,now_ns=100,expires_ns=200)
                if attack:
                    wrong=Scope("other","owner","a"*64,"b"*64)
                    return m.recall(catalog,wrong,now_ns=150)==()
                count=len(m.recall(catalog,scope,now_ns=150))
                removed=m.forget(catalog,scope,"doc",revision=1,now_ns=160)
                return count==1 and removed["tombstoned"] and not removed["physical_payload_erasure_proved"]
    if operation=="privacy":
        from .metrics import Metrics
        sink=Metrics(maximum=2)
        if attack:
            try:m.record(sink,"token_leak",elapsed_ms=100)
            except CognitionError:return True
            return False
        m.record(sink,"accepted",elapsed_ms=100)
        data=m.snapshot(sink)
        return data["sample_count"]==1 and data["secret_bytes_stored"]==0
    if operation=="evaluate":
        from .evaluation import EvaluationCase
        cases=tuple(EvaluationCase("case"+str(i),"a"*64,"b"*64,
                    "b"*64 if i%2 else "c"*64,True) for i in range(8))
        if attack:
            try:m.run(({"not":"a receipt"},))
            except CognitionError:return True
            return False
        result=m.run(cases)
        return result["passed"]==4 and result["wilson_lower"]<.5
    if operation=="audit":
        from .audit import Audit
        if attack:
            try:m.append(None,"event",{})
            except CognitionError:return True
            return False
        ledger=Audit("local");m.append(ledger,"first",{"sha":"a"*64})
        m.append(ledger,"second",{"sha":"b"*64})
        return m.verify(ledger)["count"]==2
    if operation=="recover":
        from skeleton.testing.laptop_runtime_test_support import FakeWorker
        worker=FakeWorker();worker.spine.create("s_1")
        if not attack:worker.turn("s_1","r1","hello")
        state=m.reconcile(worker,scope,"s_1","r1","hello")
        return (state["state"]=="native-effect-unknown" and not state["auto_retry"]) if attack else (
            state["state"]=="spine-committed" and worker.generation_calls==1)
    if operation=="stream":
        value="Snow ☃ emitted"
        if attack:
            try:m.postcommit(value,"a"*64)
            except CognitionError:return True
            return False
        body=m.drain(m.postcommit(value,hash_bytes(value.encode("utf-8")),frame_bytes=5,credit=1))
        return "".join(v["text"] for v in body["frames"])==value and not body["native_live_streaming_proved"]
    if operation=="tool":
        if attack:
            try:m.request(scope,request_id="r1",tool="shell",
                          args={"source_id":"doc","limit":1},expires_ns=200)
            except CognitionError:return True
            return False
        intent=m.request(scope,request_id="r1",tool="read_source",
                         args={"source_id":"doc","limit":1},expires_ns=200)
        return m.status(intent,scope,now_ns=150)["executable"] is False
    if operation=="checkpoint":
        from .audit import Audit
        if attack:
            try:m.capture(None,scope,"a"*64)
            except CognitionError:return True
            return False
        chain=Audit("local");chain.record("created",{"id":"source"})
        item=m.capture(chain,scope,"c"*64)
        return len(item["sha256"])==64 and item["external_checkpoint_signature"] is False
    if operation=="health":
        from .budget import Resource
        if attack:
            try:m.resources(None,Resource(1,1,1,1))
            except CognitionError:return True
            return False
        result=m.resources(Resource(1024,10000,5000,4),
                           Resource(128,1000,100,1))
        return result["admitted"] and result["laptop_device_qualified"] is False
    raise CognitionError("unknown operation")
