# Transactional Weather Rescue Authoring

`python -m skeleton scene-weather-rescue-author demo` changes the original
canal medic's earned shelter reward from 25 to 30 and replays the real
weather-gated journey. `edit --source-json ... --operations-json ...
--expected-digest ... --actions-json ...` supports up to 16 atomic edits
of NPC reward, deadline, storm-exposure tolerance, origin or shelter.

The source digest fences concurrent edits. All changes are validated
against canonical world topology, mission deadlines, replay budgets and
the same scene/weather runtime used by players. A no-op, stale source,
unknown NPC, impossible shelter, invalid reward or forged preview rejects
the entire transaction without modifying the original source.

`verify --source-json ... --receipt-json ...` independently reexecutes
the edit transaction and every preview action, including NPC exposure,
weather gates, scene inventory, reward settlement and save lineage.
Offline integrity is not a signature, copyright proof or device certificate.
