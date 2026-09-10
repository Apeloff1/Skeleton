    def _phase_support(self) -> None:
        """Wire the support fabric — the mirror web overseeing the contexts.

        Sits after contexts (primaries live) and before cortex (so cortex
        observes support + overseer events). Handles:
        - support: the SupportFabric mirror web
        - loader: the on-demand LoadingQueue (minimal resident footprint)
        - agentic_rag: the autonomous retrieval controller
        - overseer: the spanning multi-graph oversight module
        """
        self.report.phases.append("support")
        from skeleton.support import SupportFabric

        quad = self.handles.get("quad")
        sam = None
        # Jeeves isn't built in genesis; SAM arrives later via wire_from_genesis.
        support = SupportFabric(bus=self.bus, quad=quad, sam=sam)

        self._wire("support", "support", support)
        self._wire("support", "loader", support.loader)
        if support.agentic_rag is not None:
            self._wire("support", "agentic_rag", support.agentic_rag)
        self._wire("support", "overseer", support.overseer)

        assert self.lattice is not None
        self.lattice.register(Invariant(
            name="support_loader_bounded",
            subject="support.loader",
            snapshot=lambda: len(support.loader.resident_planes()),
            predicate=lambda resident: resident <= support.loader.max_resident,
        ))
        self.report.invariants_registered += 1
