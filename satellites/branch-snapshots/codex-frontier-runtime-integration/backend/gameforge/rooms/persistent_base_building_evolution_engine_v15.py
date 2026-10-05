class PersistentBaseBuildingEvolutionEngineV15:
    def __init__(self):
        self.room_upgrades = {}
        self.room_defenses = {}
        self.room_history = {}
        self.room_strategic_value = {}
        self.room_alliances = {}
        self.room_threat_level = {}
        self.room_specializations = {}
        self.room_automation_level = {}
        self.room_development_history = {}
        self.room_collaboration_network = {}
        self.room_evolution_paths = {}
        self.room_legacy_projects = {}
        self.room_knowledge_base = {}
        self.room_diplomacy = {}
        self.room_conflicts = {}
        self.room_infrastructure = {}
        self.room_research_labs = {}

    def build_research_lab(self, room_id: str, lab_type: str):
        if room_id not in self.room_research_labs:
            self.room_research_labs[room_id] = []
        self.room_research_labs[room_id].append(lab_type)
