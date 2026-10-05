{
  "description": "Generator for room manifests across all 1000 rooms in Zaibatsu CNS",
  "version": "1.0",
  "rooms": [
    {
      "room_id": "room_research_001",
      "category": "research",
      "neuron_type": "specialist",
      "max_seats": 8,
      "synergy_priority": ["engineering", "worldgen"]
    },
    {
      "room_id": "room_engineering_001",
      "category": "engineering",
      "neuron_type": "builder",
      "max_seats": 10,
      "synergy_priority": ["research", "asset_pipeline"]
    }
  ],
  "total_rooms": 1000,
  "note": "Full manifest would contain all 1000 rooms. This is a structural template."
}