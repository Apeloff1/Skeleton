    def wire_from_genesis(self, genesis: Any) -> None:
        """Populate state handles from a booted genesis."""
        self.genesis = genesis
        self.forge = genesis.handles.get("forge")
        self.mesh = genesis.handles.get("mesh")
        self.memory_trinity = genesis.handles.get("trinity")
        self.intelligence = genesis.handles.get("orchestrator")
        self.resilience = genesis.handles.get("fortress")

        # Pipelines
        from skeleton.pipelines import AnimationPipeline, GameForge, GameLogicPipeline, NPCPipeline
        self.npc_pipeline = NPCPipeline()
        self.game_logic_pipeline = GameLogicPipeline()
        self.animation_pipeline = AnimationPipeline()
        self.gameforge = GameForge(genesis=genesis, bus=genesis.bus)

        # Jeeves with provider-backed responses and quad retriever context
        from skeleton.jeeves import JeevesCore
        self.jeeves = JeevesCore(bus=genesis.bus, retriever=genesis.handles.get("quad"))

        # Jeeves memory matrices (served at /jeeves/matrices/{session_id})
        self.jeeves_sam = self.jeeves.sam
        self.jeeves_clom = self.jeeves.clom
        self.jeeves_krem = self.jeeves.krem
        self.jeeves_memory = self.jeeves._memory

        # Live cortex attaches to the genesis bus
        from skeleton.cortex import live
        self.cockpit = live.attach(genesis.bus)

        # Health + metrics
        from skeleton.observability import MetricsCollector
        self.metrics = MetricsCollector()
        self.health = type("Health", (), {
            "liveness": staticmethod(lambda: {"alive": True}),
            "readiness": staticmethod(lambda: {"ready": True, "subsystems": len(genesis.handles)}),
        })()
        self.ledger = genesis.handles.get("provenance")
        self.scheduler = genesis.handles.get("repetition")
        self.registry = genesis.handles.get("lattice")
