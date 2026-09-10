    def _phase_support(self) -> None:
        """Wire the support fabric + full engine stack (V1 → V3.5).

        Handles: support, loader, agentic_rag, overseer, engine,
        engine_v2, engine_v3, engine_v35. All engines bind the same
        consumers — V3.5 ticks last so its over-achiever control
        (MPC + energy + fleet ceiling) is authoritative.
        """
        self.report.phases.append("support")
        from skeleton.support import SupportFabric
        from skeleton.overseer import (
            OverseerEngine,
            OverseerEngineV2,
            OverseerEngineV3,
            OverseerEngineV35,
        )

        quad = self.handles.get("quad")
        support = SupportFabric(bus=self.bus, quad=quad)
        engine = OverseerEngine(bus=self.bus)
        engine_v2 = OverseerEngineV2(bus=self.bus)
        engine_v3 = OverseerEngineV3(bus=self.bus)

        # V3.5: fleet-attached when galaxy is live
        node = self.handles.get("galaxy")
        transport = self.handles.get("galaxy_transport")
        consensus = self.handles.get("consensus")
        engine_v35 = OverseerEngineV35(
            bus=self.bus, node=node, transport=transport, consensus=consensus,
        )

        for eng in (engine, engine_v2, engine_v3, engine_v35):
            eng.bind_loader(support.loader)
        fabric = self.handles.get("fabric")
        if fabric is not None:
            for eng in (engine, engine_v2, engine_v3, engine_v35):
                eng.bind_queue(fabric.queue)
                eng.bind_miner(fabric.backlog)
        if support.agentic_rag is not None:
            for eng in (engine, engine_v2, engine_v3, engine_v35):
                eng.bind_rag(support.agentic_rag)

        self._wire("support", "support", support)
        self._wire("support", "loader", support.loader)
        if support.agentic_rag is not None:
            self._wire("support", "agentic_rag", support.agentic_rag)
        self._wire("support", "overseer", support.overseer)
        self._wire("support", "engine", engine)
        self._wire("support", "engine_v2", engine_v2)
        self._wire("support", "engine_v3", engine_v3)
        self._wire("support", "engine_v35", engine_v35)

        assert self.lattice is not None
        self.lattice.register(Invariant(
            name="support_loader_bounded",
            subject="support.loader",
            snapshot=lambda: len(support.loader.resident_planes()),
            predicate=lambda resident: resident <= support.loader.max_resident,
        ))
        self.report.invariants_registered += 1

        engine.engine_tick()
        engine_v2.tick()
        engine_v3.tick()
        engine_v35.tick()
