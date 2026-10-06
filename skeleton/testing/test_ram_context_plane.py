from __future__ import annotations

from datetime import datetime, timedelta, timezone
import struct

from skeleton.ai.assistant.context import ContextCompiler
from skeleton.ai.assistant.contracts import AssistantRequest, ContextCandidate, TrustTier
from skeleton.kernel.ram.context_plane import (
    ContextMemoryPlane,
    ContextMemoryPolicy,
    MemoryPressure,
)
from skeleton.kernel.ram.topology import (
    MemoryAttachment,
    MemoryDevice,
    MemoryTopology,
    parse_memory_technology,
    parse_smbios_memory_devices,
)

GIB = 1024**3
NOW = datetime(2026, 10, 6, tzinfo=timezone.utc)


def _topology(
    technology: str | None = None,
    *,
    attachment: MemoryAttachment = MemoryAttachment.MODULE,
) -> MemoryTopology:
    devices = ()
    if technology:
        devices = (
            MemoryDevice(
                parse_memory_technology(technology),
                capacity_bytes=32 * GIB,
                form_factor="Chip" if attachment is MemoryAttachment.BOARD else "DIMM",
                attachment=attachment,
                source="test",
            ),
        )
    return MemoryTopology(32 * GIB, 24 * GIB, devices, "test", "test")


def _policy(**updates) -> ContextMemoryPolicy:
    values = dict(
        host_fraction=0.50,
        silicon_fraction=0.60,
        board_fraction=0.70,
        hbm_fraction=0.80,
        cxl_fraction=0.65,
        min_os_reserve_bytes=0,
        os_reserve_fraction=0.0,
        max_capacity_bytes=64 * GIB,
    )
    values.update(updates)
    return ContextMemoryPolicy(**values)


def _candidate(
    source_id: str,
    content: str,
    *,
    trust: TrustTier = TrustTier.PUBLIC_EVIDENCE,
    data_class: str = "internal",
    expires_at: datetime | None = None,
) -> ContextCandidate:
    return ContextCandidate(
        source_id=source_id,
        content=content,
        trust=trust,
        relevance=0.9,
        priority=500,
        provenance=("test:ram-context",),
        observed_at=NOW,
        expires_at=expires_at,
        data_class=data_class,
    )


def _request(
    request_id: str,
    *,
    tenant: str = "tenant-a",
    project: str = "project-a",
) -> AssistantRequest:
    return AssistantRequest(
        request_id=request_id,
        text="Continue.",
        tenant_id=tenant,
        metadata={"project_id": project},
        created_at=NOW,
        max_context_chars=64_000,
    )


def _type17(code: int, form: int, size_mb: int, locator: str) -> bytes:
    data = bytearray(0x28)
    data[0], data[1] = 17, len(data)
    struct.pack_into("<H", data, 2, 1)
    struct.pack_into("<H", data, 0x0C, size_mb)
    data[0x0E], data[0x10], data[0x11], data[0x12] = form, 1, 2, code
    return bytes(data) + locator.encode() + b"\0BANK 0\0\0"


def test_memory_parser_accepts_present_and_future_generations() -> None:
    assert parse_memory_technology("DDR5").canonical == "DDR5"
    assert parse_memory_technology("DDR6").canonical == "DDR6"
    assert parse_memory_technology("LPDDR7X").canonical == "LPDDR7X"
    assert parse_memory_technology("HBM4E").canonical == "HBM4E"


def test_smbios_finds_board_and_package_memory() -> None:
    blob = (
        _type17(0x22, 0x05, 8192, "MEMORY DOWN")
        + _type17(0x24, 0x10, 4096, "PACKAGE HBM")
        + bytes((127, 4, 0, 0)) + b"\0\0"
    )
    devices = parse_smbios_memory_devices(blob)
    assert [d.technology.canonical for d in devices] == ["DDR5", "HBM3"]
    assert devices[0].attachment is MemoryAttachment.BOARD
    assert devices[1].attachment is MemoryAttachment.PACKAGE
    assert devices[0].capacity_bytes == 8 * GIB


def test_board_and_hbm_memory_increase_hot_context_budget() -> None:
    host = ContextMemoryPlane(topology=_topology(), policy=_policy())
    dimm = ContextMemoryPlane(topology=_topology("DDR5"), policy=_policy())
    board = ContextMemoryPlane(
        topology=_topology("LPDDR7X", attachment=MemoryAttachment.BOARD),
        policy=_policy(),
    )
    hbm = ContextMemoryPlane(
        topology=_topology("HBM4E", attachment=MemoryAttachment.PACKAGE),
        policy=_policy(),
    )
    assert host.capacity_bytes < dimm.capacity_bytes < board.capacity_bytes < hbm.capacity_bytes
    assert board.backend == "board-or-package-memory"
    assert hbm.backend == "hbm-system-memory"
    assert hbm.stats()["preallocated_bytes"] == 0
    assert hbm.stats()["os_addressable_only"] is True


def test_pressure_evicts_low_value_then_pinned_context_on_emergency() -> None:
    plane = ContextMemoryPlane(
        topology=_topology(),
        policy=_policy(
            max_capacity_bytes=180,
            max_entry_bytes=512,
            compression_threshold_bytes=10_000,
        ),
    )
    plane.put("p", "pinned", b"a" * 100, priority=1000, pinned=True)
    plane.put("p", "old", b"b" * 80, priority=1)
    plane.put("p", "new", b"c" * 80, priority=10)
    assert plane.get("p", "pinned") == b"a" * 100
    assert plane.get("p", "old") is None
    assert plane.get("p", "new") == b"c" * 80

    assert plane.refresh_pressure(available_bytes=40, total_bytes=1000) is MemoryPressure.CRITICAL
    assert plane.get("p", "pinned") is None


def test_assistant_recalls_project_context_but_isolates_tenants() -> None:
    plane = ContextMemoryPlane(
        topology=_topology("LPDDR7X", attachment=MemoryAttachment.BOARD),
        policy=_policy(),
    )
    compiler = ContextCompiler(memory_plane=plane)
    first = compiler.compile(
        _request("r1"),
        (_candidate("repo:file", "Important invariant."),),
        now=NOW,
    )
    assert [x.source_id for x in first.candidates] == ["repo:file"]

    recalled = compiler.compile(_request("r2"), (), now=NOW)
    assert [x.source_id for x in recalled.candidates] == ["repo:file"]

    isolated = compiler.compile(_request("r3", tenant="tenant-b"), (), now=NOW)
    assert isolated.candidates == ()


def test_ram_context_never_resurrects_policy_restricted_or_expired_data() -> None:
    plane = ContextMemoryPlane(topology=_topology("DDR5"), policy=_policy())
    compiler = ContextCompiler(memory_plane=plane)
    first = compiler.compile(
        _request("s1"),
        (
            _candidate("policy", "current control", trust=TrustTier.TRUSTED_CONTROL),
            _candidate("secret", "secret", data_class="restricted"),
            _candidate("short", "short lived", expires_at=NOW + timedelta(seconds=1)),
        ),
        now=NOW,
    )
    assert "secret" in first.omitted_source_ids

    later = compiler.compile(
        _request("s2"),
        (),
        now=NOW + timedelta(seconds=2),
    )
    assert later.candidates == ()
