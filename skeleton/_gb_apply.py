    def _phase_galaxy(self) -> None:
        """Wire the galaxy node for distributed federation.

        Sits after forge (full local stack live) and before cortex
        (so cortex observes cross-node traffic). Handles:
        - galaxy: the node with advertised capabilities
        - galaxy_transport: HTTP inbox/outbox (bind lazily)
        - consensus: Raft-lite propose/vote over the wire
        - kag_sync: anti-entropy triple replication from the quad's KAG plane
        - galaxy_bridge: cross-node task routing (local-first dispatch)
        """
        self.report.phases.append("galaxy")
        from skeleton.galaxy import GalaxyNode, NodeTransport
        from skeleton.galaxy.consensus import ConsensusEngine
        from skeleton.galaxy.kag_sync import KAGSync
        from skeleton.galaxy.galaxy_bridge import GalaxyBridge

        node = GalaxyNode(address="127.0.0.1", bus=self.bus)
        node.add_capability("reasoning")
        node.add_capability("retrieval")
        node.add_capability("forge")
        transport = NodeTransport(node)
        consensus = ConsensusEngine(node, transport, bus=self.bus)

        quad = self.handles.get("quad")
        if quad is not None:
            kag = quad._planes.get("kag")
            if kag is not None:
                kag_sync = KAGSync(kag, node, transport, consensus=consensus, bus=self.bus)
                self._wire("galaxy", "kag_sync", kag_sync)

        # Cross-node task routing rides the local mesh bridge
        mesh_bridge = self.handles.get("bridge")
        if mesh_bridge is not None:
            galaxy_bridge = GalaxyBridge(mesh_bridge, node, transport, bus=self.bus)
            self._wire("galaxy", "galaxy_bridge", galaxy_bridge)

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
