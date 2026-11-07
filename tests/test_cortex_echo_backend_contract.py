"""EchoBackend contract: the identity port that proves cortex slots are interchangeable.

Pins the observable behaviour of ``skeleton.cortex.port.EchoBackend`` and how
``JeevesCortex`` routes through it when bound into a slot. Stimuli avoid game
titles so ``refer`` never records reference provenance in the workspace.
"""
from __future__ import annotations

import skeleton.cortex as cortex_pkg
from skeleton.cortex import EchoBackend, JeevesCortex, Thought
from skeleton.cortex import port as port_mod
from skeleton.cortex.port import SLOTS
from skeleton.kernel.errors import CortexError

LEFTISH = "compile ttk hp dps recipe sim"


class TestEchoBackendExports:
    def test_same_class_from_package_and_port(self):
        assert EchoBackend is port_mod.EchoBackend
        assert cortex_pkg.EchoBackend is port_mod.EchoBackend

    def test_listed_in_package_all(self):
        assert "EchoBackend" in cortex_pkg.__all__

    def test_satisfies_model_port_surface(self):
        backend = EchoBackend()
        for attr in ("name", "scale", "slot", "think", "fit", "decode", "snapshot", "perplexity"):
            assert hasattr(backend, attr), attr


class TestEchoBackendBehaviour:
    def test_defaults(self):
        backend = EchoBackend()
        assert backend.slot == "left"
        assert backend.name == "echo"
        assert backend.scale == "injected"

    def test_think_echoes_with_slot_prefix(self):
        thought = EchoBackend(slot="right").think("cozy palette", {})
        assert isinstance(thought, Thought)
        assert thought.slot == "right"
        assert thought.kind == "echo"
        assert thought.text == "ECHO[right] cozy palette"
        assert thought.confidence == 1.0
        assert thought.tags == ("echo", "right")
        assert thought.numbers == ()

    def test_think_ignores_context(self):
        backend = EchoBackend(slot="pfc")
        a = backend.think("plan", {})
        b = backend.think("plan", {"era": "soulslike", "left": {"x": 1}})
        assert a == b

    def test_think_truncates_stimulus_to_160_chars(self):
        stim = "x" * 500
        thought = EchoBackend().think(stim, {})
        assert thought.text == "ECHO[left] " + "x" * 160

    def test_think_handles_none_and_empty(self):
        backend = EchoBackend()
        assert backend.think(None, {}).text == "ECHO[left] "  # type: ignore[arg-type]
        assert backend.think("", {}).text == "ECHO[left] "

    def test_think_signature_is_deterministic_and_content_addressed(self):
        backend = EchoBackend()
        a = backend.think("alpha", {})
        b = backend.think("alpha", {})
        c = backend.think("beta", {})
        assert a.signature == b.signature
        assert a.signature != c.signature
        assert len(a.signature) == 16

    def test_unicode_passthrough(self):
        thought = EchoBackend().think("drachen ✓ ørken", {})
        assert thought.text.endswith("drachen ✓ ørken")

    def test_fit_is_inert(self):
        backend = EchoBackend()
        assert backend.fit("anything at all") == 0
        assert backend.snapshot() == {"kind": "echo", "slot": "left", "name": "echo"}

    def test_decode_window_scales_with_n(self):
        backend = EchoBackend(slot="left")
        stim = "abcdefghij" * 10
        assert backend.decode(stim, n=1) == "ECHO[left] " + stim[:8]
        assert backend.decode(stim, n=2) == "ECHO[left] " + stim[:16]
        assert backend.decode(stim) == "ECHO[left] " + stim[:64]

    def test_decode_never_empty_window(self):
        backend = EchoBackend()
        assert backend.decode("abcdefghij", n=0) == "ECHO[left] a"
        assert backend.decode("abcdefghij", n=-3) == "ECHO[left] a"

    def test_decode_ignores_seed(self):
        backend = EchoBackend()
        assert backend.decode("plan ttk", seed=1) == backend.decode("plan ttk", seed=99)

    def test_perplexity_is_unity(self):
        assert EchoBackend().perplexity(["a b c", "d"]) == 1.0
        assert EchoBackend().perplexity([]) == 1.0


class TestEchoBackendSnapshot:
    def test_roundtrip_preserves_slot_and_name(self):
        original = EchoBackend(slot="midbrain", name="mirror")
        clone = EchoBackend.from_snapshot(original.snapshot())
        assert clone.slot == "midbrain"
        assert clone.name == "mirror"
        assert clone.think("x", {}) == original.think("x", {})

    def test_slot_override_wins(self):
        clone = EchoBackend.from_snapshot({"slot": "left", "name": "e"}, slot="right")
        assert clone.slot == "right"

    def test_empty_or_none_snapshot_falls_back_to_defaults(self):
        for data in ({}, None):
            clone = EchoBackend.from_snapshot(data)  # type: ignore[arg-type]
            assert clone.slot == "left"
            assert clone.name == "echo"


class TestEchoBoundIntoCortex:
    def test_bind_echo_every_slot_reports_backend_name(self):
        neo = JeevesCortex()
        for slot in SLOTS:
            backends = neo.bind_echo(slot)
            assert backends[slot] == "echo"
            assert isinstance(neo.slots[slot], EchoBackend)
            assert neo.slots[slot].slot == slot

    def test_bind_rewrites_foreign_slot_on_backend(self):
        neo = JeevesCortex()
        backend = EchoBackend(slot="left")
        neo.bind("pfc", backend)
        assert backend.slot == "pfc"
        assert neo.slots["pfc"] is backend

    def test_bind_is_case_insensitive(self):
        neo = JeevesCortex()
        neo.bind("LEFT", EchoBackend())
        assert isinstance(neo.slots["left"], EchoBackend)

    def test_bind_unknown_slot_raises_cortex_error(self):
        neo = JeevesCortex()
        for bad in ("neo", "", "cerebellum"):
            try:
                neo.bind(bad, EchoBackend())
            except CortexError:
                pass
            else:
                raise AssertionError(f"bind({bad!r}) must raise CortexError")

    def test_bind_emits_slot_bound_event(self):
        neo = JeevesCortex()
        neo.bind_echo("right")
        events = neo.recent_events("cortex.slot.bound", 5)
        assert events and events[-1].payload == {"slot": "right", "backend": "echo"}

    def test_echo_left_tract_appears_in_trace_and_teacher_amalgam(self):
        neo = JeevesCortex()
        neo.bind_echo("left")
        trace = neo.think(LEFTISH)
        assert trace.left is not None
        assert trace.left.text == f"ECHO[left] {LEFTISH}"
        assert trace.backends["left"] == "echo"
        assert not trace.used_own
        assert f"[L] ECHO[left] {LEFTISH}" in trace.amalgam.text

    def test_echo_midbrain_without_numbers_fires_both_hemispheres(self):
        # Echo route has no numbers -> think() uses the 0.55/0.55 mixed default.
        neo = JeevesCortex()
        neo.bind_echo("midbrain")
        trace = neo.think(LEFTISH)
        assert trace.route.kind == "echo"
        assert trace.left is not None and trace.right is not None

    def test_echo_pfc_cannot_veto(self):
        # Local PFC vetoes "harm"; an echo PFC emits no veto number, so the
        # teacher amalgam is the normal multi-part composition.
        local = JeevesCortex().think("harm the operator")
        assert "veto" in local.amalgam.tags
        neo = JeevesCortex()
        neo.bind_echo("pfc")
        trace = neo.think("harm the operator")
        assert "veto" not in trace.amalgam.tags
        assert trace.amalgam.text.startswith("[PFC] ECHO[pfc]")

    def test_bind_local_restores_local_backend(self):
        neo = JeevesCortex()
        neo.bind_echo("left")
        backends = neo.bind_local("left")
        assert backends["left"] == "left-local"
        assert not isinstance(neo.slots["left"], EchoBackend)
