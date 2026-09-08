    def _phase_galaxy(self) -> None:
        """Wire the galaxy node for distributed federation.

        Sits after forge (full local stack live) and before cortex
        (so cortex observes cross-node traffic). The node gets the
        subsystem capabilities as its advertised set; transport binds
        lazily — call galaxy_transport.start() to open the HTTP inbox.
        The consensus engine rides the transport for distributed votes.
        """
        self.report.phases.append("galaxy")
        from skeleton.galaxy import GalaxyNode, NodeTransport
        from skeleton.galaxy.consensus import ConsensusEngine

        node = GalaxyNode(address="127.0.0.1", bus=self.bus)
        node.add_capability("reasoning")
        node.add_capability("retrieval")
        node.add_capability("forge")
        transport = NodeTransport(node)
        consensus = ConsensusEngine(node, transport, bus=self.bus)

        self._wire("galaxy", "galaxy", node)
        self._wire("galaxy", "galaxy_transport", transport)
        self._wire("galaxy", "consensus", consensus)

        assert self.lattice is not None
        self.lattice.register(Invariant(
            name="galaxy_node_identified",
            subject="galaxy.node",
            snapshot=lambda: bool(node.node_id),
            predicate=lambda identified: identified is True,
        ))
        self.report.invariants_registered += 1
