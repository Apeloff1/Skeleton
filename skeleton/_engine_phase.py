    def _phase_support(self) -> None:
        """Wire the support fabric — the mirror web overseeing the contexts.

        Handles: support, loader, agentic_rag, overseer, engine.
        The OverseerEngine is the hardware-specialized core: it binds
        the governor's budgets onto the loader, queue, miner, and RAG
        so every consumer fits inside the device's hardware envelope.
        """
        self.report.phases.append("support")
        from skeleton.support import SupportFabric
        from skeleton.overseer import OverseerEngine

        quad = self.handles.get("quad")
        support = SupportFabric(bus=self.bus, quad=quad)
        engine = OverseerEngine(bus=self.bus)

        # Bind budget consumers: resources follow the hardware envelope
        engine.bind_loader(support.loader)
        fabric = self.handles.get("fabric")
        if fabric is not None:
            engine.bind_queue(fabric.queue)
            engine.bind_miner(fabric.backlog)
        if support.agentic_rag is not None:
            engine.bind_rag(support.agentic_rag)

        self._wire("support", "support", support)
        self._wire("support", "loader", support.loader)
        if support.agentic_rag is not None:
            self._wire("support", "agentic_rag", support.agentic_rag)
        self._wire("support", "overseer", support.overseer)
        self._wire("support", "engine", engine)

        assert self.lattice is not None
        self.lattice.register(Invariant(
            name="support_loader_bounded",
            subject="support.loader",
            snapshot=lambda: len(support.loader.resident_planes()),
            predicate=lambda resident: resident <= support.loader.max_resident,
        ))
        self.report.invariants_registered += 1

        # First engine tick: classify this device and set initial budgets
        engine.engine_tick()
