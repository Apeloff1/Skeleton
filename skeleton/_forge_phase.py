    def _phase_forge(self) -> None:
        """Wire the universal forge as a first-class genesis handle.

        Sits after interface (verifier chain available) and before cortex
        (so cortex observes forge events). The forge owns blueprint
        composition, validation, and materialization; the verify-until-green
        loop and quality ledger plug in through its bus.
        """
        self.report.phases.append("forge")
        from skeleton.forge.universal import Forge

        forge = Forge(bus=self.bus)
        self._wire("forge", "forge", forge)

        assert self.lattice is not None
        self.lattice.register(Invariant(
            name="forge_kinds_registered",
            subject="forge",
            snapshot=lambda: len(forge.available_kinds()),
            predicate=lambda kinds: kinds >= 5,
        ))
        self.report.invariants_registered += 1
