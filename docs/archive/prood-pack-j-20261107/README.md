# Prood Pack J recovery custody

Historical source commit: `47465c4ea16e3487ea0900b15f5248b0a3da3b92`.

Three dependency-free data/planning modules are recovered in `skeleton/prood`: eras, forge_registry, swarm_planner. Other 41 modules and the historical smoke test are retained as inert text; paths end in .py.txt to avoid Python import and test discovery. Original blobs are retained, not rewritten. This is a source recovery, not an active product port.

Do not import or execute the original initializer: it installs process-global core/routes aliases, substitutes an in-memory database, and impersonates zstandard with identity codecs. Provider enrichment, write custody and duplicate backend implementation require separate adaptation and qualification. No external provider or real database is enabled.

## Original object inventory

| Original path | Source blob | Destination |
|---|---|---|
| skeleton/prood/__init__.py | 282b7605fcb1da2a8ee29826590dc1d9393deed2 | source/__init__.py.txt |
| skeleton/prood/_memory_db.py | efcb82485bcf280aaf72b8bdb16a08ec1eb7a52f | source/_memory_db.py.txt |
| skeleton/prood/agent_ledger.py | 9409bbbdbee19dd40803d5c8a9bdb237e599127a | source/agent_ledger.py.txt |
| skeleton/prood/agent_mesh.py | 9c3432d072b61831aaa3676c1b77feb94b8e7b0d | source/agent_mesh.py.txt |
| skeleton/prood/anti_farm.py | e656246af31aa9841b0a7a049830f8ccd9dec010 | source/anti_farm.py.txt |
| skeleton/prood/asset_forge.py | 64e528986e5a88fe39e3e3f2d25d8937de1dbea6 | source/asset_forge.py.txt |
| skeleton/prood/autonomous_orchestrator.py | 9a5ce719fd765760ae3e12e758f878865f55ed49 | source/autonomous_orchestrator.py.txt |
| skeleton/prood/boot_stages.py | da343c1f20f8833d36f96e358207858e31c059c8 | source/boot_stages.py.txt |
| skeleton/prood/boot_timeline.py | 79711584555236580c3c5e5421a2e312efa6fb7c | source/boot_timeline.py.txt |
| skeleton/prood/build_config.py | 9a87e465ee7b0a2e46e314e598d7ff5e8994e678 | source/build_config.py.txt |
| skeleton/prood/build_journey.py | c393d7bb860b756c4b30312898e164a98dfd6cc3 | source/build_journey.py.txt |
| skeleton/prood/build_ledger.py | 9573fa44b791b71bb319eb4faf311b2f97ac23dc | source/build_ledger.py.txt |
| skeleton/prood/build_vault.py | 1b6a112a7402bcb3e0b4f173ebcb1cd7fd2caae1 | source/build_vault.py.txt |
| skeleton/prood/build_watchdog.py | 004f1be8e28ea4d5578db2960c93b2eb248f9527 | source/build_watchdog.py.txt |
| skeleton/prood/choice_gates.py | 38094ef44c26e25b2048f029812090db692c57b6 | source/choice_gates.py.txt |
| skeleton/prood/cold_storage.py | bb14eb47e6f3758485de976840b39f58b4902ac5 | source/cold_storage.py.txt |
| skeleton/prood/collection_agents.py | e317db409a757a8eeed12e630343c78d4fcdb5c5 | source/collection_agents.py.txt |
| skeleton/prood/compressed_vault.py | efef27e587173767e84f628ffea57bef4c77a871 | source/compressed_vault.py.txt |
| skeleton/prood/construct_forge.py | eaaa403157b4d3dccfa54e591ed80515eeffd686 | source/construct_forge.py.txt |
| skeleton/prood/discourse_engine.py | 248fd61532b9f4b11eda8df3531eb59158e875cd | source/discourse_engine.py.txt |
| skeleton/prood/eras.py | 37ac752815c28240eaade24d8913763332962700 | skeleton/prood/eras.py |
| skeleton/prood/forge_dna.py | ad290b1a15af31a0a361a74bd2a3963defd36e65 | source/forge_dna.py.txt |
| skeleton/prood/forge_registry.py | db884016208ad59537508ab01a8124da70c70515 | skeleton/prood/forge_registry.py |
| skeleton/prood/forge_validator.py | d37b9de2a05c23df767c1496c934fca6d92d0d20 | source/forge_validator.py.txt |
| skeleton/prood/full_roster.py | 1932b501a9cd6dce5b6572bec6fb52b825c071f4 | source/full_roster.py.txt |
| skeleton/prood/game_choices.py | 1c24c52b327a4d8da0eeaf4c2c18e4458e93ec8e | source/game_choices.py.txt |
| skeleton/prood/game_knowledge_vault.py | 9bc9f1e67845cd5a7e5e61f035b74d20b6f7951d | source/game_knowledge_vault.py.txt |
| skeleton/prood/item_foundry.py | 77b618a5afa167f6bce9a5b3e83b11352f8056d8 | source/item_foundry.py.txt |
| skeleton/prood/lazy_registry.py | c7e9f68e67db302addbe7b4b13afc875a1148066 | source/lazy_registry.py.txt |
| skeleton/prood/playable_game.py | cd0efb9c8ceb05654acd223d3d98511382750945 | source/playable_game.py.txt |
| skeleton/prood/provenance_ledger.py | 4780ea79e804575a6d164bae21d278d5e948be17 | source/provenance_ledger.py.txt |
| skeleton/prood/refine_gates.py | 2b0870cfa3b8dd89e4582ad5ef68af3fccf6d415 | source/refine_gates.py.txt |
| skeleton/prood/runtime_health.py | 9a43a176a417b2e7e39921d81af439bf0fdf5477 | source/runtime_health.py.txt |
| skeleton/prood/stage_builder.py | 85776f9c324b0d435fd3ac3efafa6b787a5c9a0f | source/stage_builder.py.txt |
| skeleton/prood/stage_vault.py | 5f87eb5bdd11add333d1fdf5f37d6a81dced57c9 | source/stage_vault.py.txt |
| skeleton/prood/swarm_planner.py | adfbf1ffd302053078b621a4952d529725ac7c64 | skeleton/prood/swarm_planner.py |
| skeleton/prood/systems_forge.py | e96deb729fbe070ac722c05888fa3d3422c690a4 | source/systems_forge.py.txt |
| skeleton/prood/systems_forge_ext.py | 538f15f60f764a6ccb6499c3727b04b814f229ef | source/systems_forge_ext.py.txt |
| skeleton/prood/text_gamefile.py | b0314097c84055fce99017f7e8872318e4a0f346 | source/text_gamefile.py.txt |
| skeleton/prood/tool_forge.py | e9310be9dafd4afda445e41778afd32695765cbf | source/tool_forge.py.txt |
| skeleton/prood/tunnel_watchdog.py | 226d85a0e160f7e86d93371251d25b8e3141bba2 | source/tunnel_watchdog.py.txt |
| skeleton/prood/unbulk.py | 0d39f8b5094b9df14b5e1ac3fbe16c5b66b2077a | source/unbulk.py.txt |
| skeleton/prood/universal_forge.py | 24c71d78a4e6640374cd463239c054f66cb7924a | source/universal_forge.py.txt |
| skeleton/prood/whisper_network.py | 2a26b6371312a554811de9783faf048c9b4ca074 | source/whisper_network.py.txt |
| tests/test_pack_j_prood_deepen.py | aa290969e21f33dc12c69820e51302e18c767570 | source/test_pack_j_prood_deepen.py.txt |
