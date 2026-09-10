    def _phase_support(self) -> None:
        """Wire the support fabric + hardware-specialized engines.

        Handles: support, loader, agentic_rag, overseer, engine, engine_v2.
        V1 engine handles simple throttle budgets; V2 supersedes with
        predictive control (fusion, forecasting, PID, QoS arbitration).
        Both bind the same consumers — V2 ticks last so its controlled
        budget is authoritative.
        """
        self.report.phases.append("support")
        from skeleton.support import SupportFabric
        from skeleton.overseer import OverseerEngine, OverseerEngineV2

        quad = self.handles.get("quad")
        support = SupportFabric(bus=self.bus, quad=quad)
        engine = OverseerEngine(bus=self.bus)
        engine_v2 = OverseerEngineV2(bus=self.bus)

        # Bind budget consumers to both engines (V2 is authoritative)
        engine.bind_loader(support.loader)
        engine_v2.bind_loader(support.loader)
        fabric = self.handles.get("fabric")
        if fabric is not None:
            engine.bind_queue(fabric.queue)
            engine.bind_miner(fabric.backlog)
            engine_v2.bind_queue(fabric.queue)
            engine_v2.bind_miner(fabric.backlog)
        if support.agentic_rag is not None:
            engine.bind_rag(support.agentic_rag)
            engine_v2.bind_rag(support.agentic_rag)

        self._wire("support", "support", support)
        self._wire("support", "loader", support.loader)
        if support.agentic_rag is not None:
            self._wire("support", "agentic_rag", support.agentic_rag)
        self._wire("support", "overseer", support.overseer)
        self._wire("support", "engine", engine)
        self._wire("support", "engine_v2", engine_v2)

        assert self.lattice is not None
        self.lattice.register(Invariant(
            name="support_loader_bounded",
            subject="support.loader",
            snapshot=lambda: len(support.loader.resident_planes()),
            predicate=lambda resident: resident <= support.loader.max_resident,
        ))
        self.report.invariants_registered += 1

        # First ticks: classify the device and set initial budgets
        engine.engine_tick()
        engine_v2.tick()
