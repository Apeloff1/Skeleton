"""
core/lazy_registry.py — LAZY ACCESS TO EVERY CORE MODULE (deferred import).

Wraps all `core/*.py` modules behind lazy proxies so heavy modules
(universal_forge, systems_forge_ext, snowball_axes, the big seed data, …) are
imported ONLY on first real use — lowering cold-start RAM and import time.

Usage (drop-in, transparent):
    from core import lazy_registry as L
    L.universal_forge.forge(spec)        # universal_forge imported here, first touch
    L.snowball_axes.resolve(spec, 2)     # snowball_axes imported on first touch

PEP 562 module __getattr__ means ANY attribute access `L.<module>` returns a
lazy proxy for `core.<module>` — every core module is "wrapped" without touching
existing import sites. Already-imported modules are reused by importlib's cache,
so this never double-imports.
"""
from __future__ import annotations

import importlib
import pathlib
import sys

# Reviewed literal dispatch; update this inventory when adding core or seed modules.
_LOADERS = {
    'core.academy_product': lambda: importlib.import_module('core.academy_product'),
    'core.achievement_engine': lambda: importlib.import_module('core.achievement_engine'),
    'core.adaptive_absorption_fabric': lambda: importlib.import_module('core.adaptive_absorption_fabric'),
    'core.agent_ledger': lambda: importlib.import_module('core.agent_ledger'),
    'core.agent_mesh': lambda: importlib.import_module('core.agent_mesh'),
    'core.ai_provider': lambda: importlib.import_module('core.ai_provider'),
    'core.ai_provider_compat': lambda: importlib.import_module('core.ai_provider_compat'),
    'core.anti_farm': lambda: importlib.import_module('core.anti_farm'),
    'core.api_contract_registry': lambda: importlib.import_module('core.api_contract_registry'),
    'core.art_identity': lambda: importlib.import_module('core.art_identity'),
    'core.asset_forge': lambda: importlib.import_module('core.asset_forge'),
    'core.assurance_composition': lambda: importlib.import_module('core.assurance_composition'),
    'core.atomic_release_deployer': lambda: importlib.import_module('core.atomic_release_deployer'),
    'core.auth_security': lambda: importlib.import_module('core.auth_security'),
    'core.autonomous_orchestrator': lambda: importlib.import_module('core.autonomous_orchestrator'),
    'core.boot_stages': lambda: importlib.import_module('core.boot_stages'),
    'core.boot_timeline': lambda: importlib.import_module('core.boot_timeline'),
    'core.build_config': lambda: importlib.import_module('core.build_config'),
    'core.build_journey': lambda: importlib.import_module('core.build_journey'),
    'core.build_ledger': lambda: importlib.import_module('core.build_ledger'),
    'core.build_vault': lambda: importlib.import_module('core.build_vault'),
    'core.build_watchdog': lambda: importlib.import_module('core.build_watchdog'),
    'core.calibration_ledger': lambda: importlib.import_module('core.calibration_ledger'),
    'core.canonical_json': lambda: importlib.import_module('core.canonical_json'),
    'core.canonical_memory': lambda: importlib.import_module('core.canonical_memory'),
    'core.canonical_product_policy': lambda: importlib.import_module('core.canonical_product_policy'),
    'core.capability_readiness': lambda: importlib.import_module('core.capability_readiness'),
    'core.character_profile': lambda: importlib.import_module('core.character_profile'),
    'core.charter_policy': lambda: importlib.import_module('core.charter_policy'),
    'core.chat_attachments': lambda: importlib.import_module('core.chat_attachments'),
    'core.chat_sessions': lambda: importlib.import_module('core.chat_sessions'),
    'core.chat_turn_lifecycle': lambda: importlib.import_module('core.chat_turn_lifecycle'),
    'core.chat_turns': lambda: importlib.import_module('core.chat_turns'),
    'core.choice_gates': lambda: importlib.import_module('core.choice_gates'),
    'core.churn_2_service': lambda: importlib.import_module('core.churn_2_service'),
    'core.citation_integrity': lambda: importlib.import_module('core.citation_integrity'),
    'core.claim_dependency_graph': lambda: importlib.import_module('core.claim_dependency_graph'),
    'core.claim_identity': lambda: importlib.import_module('core.claim_identity'),
    'core.claim_proof': lambda: importlib.import_module('core.claim_proof'),
    'core.claim_truth_ledger': lambda: importlib.import_module('core.claim_truth_ledger'),
    'core.cockpit_execution_projection': lambda: importlib.import_module('core.cockpit_execution_projection'),
    'core.cold_storage': lambda: importlib.import_module('core.cold_storage'),
    'core.collection_agents': lambda: importlib.import_module('core.collection_agents'),
    'core.compressed_vault': lambda: importlib.import_module('core.compressed_vault'),
    'core.construct_forge': lambda: importlib.import_module('core.construct_forge'),
    'core.content_store': lambda: importlib.import_module('core.content_store'),
    'core.contradiction_resolver': lambda: importlib.import_module('core.contradiction_resolver'),
    'core.control_plane': lambda: importlib.import_module('core.control_plane'),
    'core.control_plane_deployment': lambda: importlib.import_module('core.control_plane_deployment'),
    'core.conversations': lambda: importlib.import_module('core.conversations'),
    'core.course_runtime': lambda: importlib.import_module('core.course_runtime'),
    'core.crafting_engine': lambda: importlib.import_module('core.crafting_engine'),
    'core.creature_ai': lambda: importlib.import_module('core.creature_ai'),
    'core.crew_runtime': lambda: importlib.import_module('core.crew_runtime'),
    'core.curiosity_engine': lambda: importlib.import_module('core.curiosity_engine'),
    'core.curiosity_research_pipeline': lambda: importlib.import_module('core.curiosity_research_pipeline'),
    'core.curiosity_service': lambda: importlib.import_module('core.curiosity_service'),
    'core.deployment_authorization': lambda: importlib.import_module('core.deployment_authorization'),
    'core.deployment_checkpoint_assurance': lambda: importlib.import_module('core.deployment_checkpoint_assurance'),
    'core.deployment_checkpoint_ledger': lambda: importlib.import_module('core.deployment_checkpoint_ledger'),
    'core.deployment_checkpoint_pin_config': lambda: importlib.import_module('core.deployment_checkpoint_pin_config'),
    'core.deployment_checkpoint_pin_diagnostics': lambda: importlib.import_module('core.deployment_checkpoint_pin_diagnostics'),
    'core.deployment_checkpoint_pin_ledger': lambda: importlib.import_module('core.deployment_checkpoint_pin_ledger'),
    'core.deployment_checkpoint_pin_runtime': lambda: importlib.import_module('core.deployment_checkpoint_pin_runtime'),
    'core.deployment_checkpoint_pin_wire': lambda: importlib.import_module('core.deployment_checkpoint_pin_wire'),
    'core.deployment_checkpoint_policy_rotation': lambda: importlib.import_module('core.deployment_checkpoint_policy_rotation'),
    'core.deployment_checkpoint_policy_verifier': lambda: importlib.import_module('core.deployment_checkpoint_policy_verifier'),
    'core.deployment_checkpoint_proof': lambda: importlib.import_module('core.deployment_checkpoint_proof'),
    'core.deployment_checkpoint_target': lambda: importlib.import_module('core.deployment_checkpoint_target'),
    'core.deployment_checkpoint_trust_advance': lambda: importlib.import_module('core.deployment_checkpoint_trust_advance'),
    'core.deployment_checkpoint_trust_policy': lambda: importlib.import_module('core.deployment_checkpoint_trust_policy'),
    'core.deployment_checkpoint_trust_wire': lambda: importlib.import_module('core.deployment_checkpoint_trust_wire'),
    'core.deployment_checkpoint_verification_package': lambda: importlib.import_module('core.deployment_checkpoint_verification_package'),
    'core.deployment_checkpoint_witness': lambda: importlib.import_module('core.deployment_checkpoint_witness'),
    'core.deployment_checkpoint_witnessed_continuity': lambda: importlib.import_module('core.deployment_checkpoint_witnessed_continuity'),
    'core.deployment_evidence_checkpoint': lambda: importlib.import_module('core.deployment_evidence_checkpoint'),
    'core.deployment_gateway': lambda: importlib.import_module('core.deployment_gateway'),
    'core.deployment_planner': lambda: importlib.import_module('core.deployment_planner'),
    'core.deployment_preflight': lambda: importlib.import_module('core.deployment_preflight'),
    'core.deployment_proof': lambda: importlib.import_module('core.deployment_proof'),
    'core.deployment_proof_diagnostics': lambda: importlib.import_module('core.deployment_proof_diagnostics'),
    'core.deployment_receipts': lambda: importlib.import_module('core.deployment_receipts'),
    'core.dialogue_runtime': lambda: importlib.import_module('core.dialogue_runtime'),
    'core.director_agent': lambda: importlib.import_module('core.director_agent'),
    'core.discourse_engine': lambda: importlib.import_module('core.discourse_engine'),
    'core.discovery_engine': lambda: importlib.import_module('core.discovery_engine'),
    'core.dragon_conversation_binding': lambda: importlib.import_module('core.dragon_conversation_binding'),
    'core.dragon_crawler': lambda: importlib.import_module('core.dragon_crawler'),
    'core.dragon_delivery_routes': lambda: importlib.import_module('core.dragon_delivery_routes'),
    'core.dragon_reference_practice': lambda: importlib.import_module('core.dragon_reference_practice'),
    'core.dragon_research_session': lambda: importlib.import_module('core.dragon_research_session'),
    'core.dragon_research_startup': lambda: importlib.import_module('core.dragon_research_startup'),
    'core.dragon_runtime': lambda: importlib.import_module('core.dragon_runtime'),
    'core.dragon_runtime_bridge': lambda: importlib.import_module('core.dragon_runtime_bridge'),
    'core.durable_outbox': lambda: importlib.import_module('core.durable_outbox'),
    'core.economy_runtime': lambda: importlib.import_module('core.economy_runtime'),
    'core.engine_chat': lambda: importlib.import_module('core.engine_chat'),
    'core.engine_client': lambda: importlib.import_module('core.engine_client'),
    'core.engine_text': lambda: importlib.import_module('core.engine_text'),
    'core.environment_runtime': lambda: importlib.import_module('core.environment_runtime'),
    'core.epistemic_attestation': lambda: importlib.import_module('core.epistemic_attestation'),
    'core.epistemic_checkpoint': lambda: importlib.import_module('core.epistemic_checkpoint'),
    'core.epistemic_claim_index': lambda: importlib.import_module('core.epistemic_claim_index'),
    'core.epistemic_gate': lambda: importlib.import_module('core.epistemic_gate'),
    'core.epistemic_transparency': lambda: importlib.import_module('core.epistemic_transparency'),
    'core.epistemic_trust_runtime': lambda: importlib.import_module('core.epistemic_trust_runtime'),
    'core.eras': lambda: importlib.import_module('core.eras'),
    'core.evidence_registry': lambda: importlib.import_module('core.evidence_registry'),
    'core.evolution_policy': lambda: importlib.import_module('core.evolution_policy'),
    'core.exec_guard': lambda: importlib.import_module('core.exec_guard'),
    'core.execution_evidence': lambda: importlib.import_module('core.execution_evidence'),
    'core.execution_receipts': lambda: importlib.import_module('core.execution_receipts'),
    'core.expressive_tts': lambda: importlib.import_module('core.expressive_tts'),
    'core.feature_flags': lambda: importlib.import_module('core.feature_flags'),
    'core.feature_flags_audit': lambda: importlib.import_module('core.feature_flags_audit'),
    'core.feature_flags_metrics': lambda: importlib.import_module('core.feature_flags_metrics'),
    'core.file_lease': lambda: importlib.import_module('core.file_lease'),
    'core.final_build': lambda: importlib.import_module('core.final_build'),
    'core.flight_dynamics': lambda: importlib.import_module('core.flight_dynamics'),
    'core.forge_dna': lambda: importlib.import_module('core.forge_dna'),
    'core.forge_quality': lambda: importlib.import_module('core.forge_quality'),
    'core.forge_registry': lambda: importlib.import_module('core.forge_registry'),
    'core.forge_validator': lambda: importlib.import_module('core.forge_validator'),
    'core.full_roster': lambda: importlib.import_module('core.full_roster'),
    'core.game_frontier_authoring': lambda: importlib.import_module('core.game_frontier_authoring'),
    'core.game_choices': lambda: importlib.import_module('core.game_choices'),
    'core.game_console_build': lambda: importlib.import_module('core.game_console_build'),
    'core.game_console_studio': lambda: importlib.import_module('core.game_console_studio'),
    'core.game_content_uploads': lambda: importlib.import_module('core.game_content_uploads'),
    'core.game_knowledge_vault': lambda: importlib.import_module('core.game_knowledge_vault'),
    'core.game_learning': lambda: importlib.import_module('core.game_learning'),
    'core.game_learning_events': lambda: importlib.import_module('core.game_learning_events'),
    'core.game_play': lambda: importlib.import_module('core.game_play'),
    'core.game_session': lambda: importlib.import_module('core.game_session'),
    'core.game_studio_agent': lambda: importlib.import_module('core.game_studio_agent'),
    'core.game_studio_health': lambda: importlib.import_module('core.game_studio_health'),
    'core.game_studio_learning': lambda: importlib.import_module('core.game_studio_learning'),
    'core.game_studio_review': lambda: importlib.import_module('core.game_studio_review'),
    'core.game_studio_tools': lambda: importlib.import_module('core.game_studio_tools'),
    'core.game_successor': lambda: importlib.import_module('core.game_successor'),
    'core.gamefile_pipeline': lambda: importlib.import_module('core.gamefile_pipeline'),
    'core.gameforge_artifact_builder': lambda: importlib.import_module('core.gameforge_artifact_builder'),
    'core.http_errors': lambda: importlib.import_module('core.http_errors'),
    'core.idle_curiosity_runtime': lambda: importlib.import_module('core.idle_curiosity_runtime'),
    'core.input_fusion': lambda: importlib.import_module('core.input_fusion'),
    'core.item_foundry': lambda: importlib.import_module('core.item_foundry'),
    'core.jeeves_capabilities': lambda: importlib.import_module('core.jeeves_capabilities'),
    'core.jeeves_control_plane': lambda: importlib.import_module('core.jeeves_control_plane'),
    'core.jeeves_execution_kernel': lambda: importlib.import_module('core.jeeves_execution_kernel'),
    'core.jeeves_memory': lambda: importlib.import_module('core.jeeves_memory'),
    'core.knowledge_augmented_jeeves': lambda: importlib.import_module('core.knowledge_augmented_jeeves'),
    'core.knowledge_fabric': lambda: importlib.import_module('core.knowledge_fabric'),
    'core.legion_discourse': lambda: importlib.import_module('core.legion_discourse'),
    'core.live_session': lambda: importlib.import_module('core.live_session'),
    'core.loop_local_asyncio': lambda: importlib.import_module('core.loop_local_asyncio'),
    'core.model_catalog': lambda: importlib.import_module('core.model_catalog'),
    'core.model_router': lambda: importlib.import_module('core.model_router'),
    'core.mongo_guard': lambda: importlib.import_module('core.mongo_guard'),
    'core.narrative_vault': lambda: importlib.import_module('core.narrative_vault'),
    'core.narrative_vault_specialized': lambda: importlib.import_module('core.narrative_vault_specialized'),
    'core.observability': lambda: importlib.import_module('core.observability'),
    'core.operation_projection': lambda: importlib.import_module('core.operation_projection'),
    'core.operation_stream_transport': lambda: importlib.import_module('core.operation_stream_transport'),
    'core.operator_control_projection': lambda: importlib.import_module('core.operator_control_projection'),
    'core.outcall_manager': lambda: importlib.import_module('core.outcall_manager'),
    'core.perf': lambda: importlib.import_module('core.perf'),
    'core.phase_gates': lambda: importlib.import_module('core.phase_gates'),
    'core.platoons': lambda: importlib.import_module('core.platoons'),
    'core.playable_game': lambda: importlib.import_module('core.playable_game'),
    'core.playable_simulation': lambda: importlib.import_module('core.playable_simulation'),
    'core.player_runtime': lambda: importlib.import_module('core.player_runtime'),
    'core.policy_repository': lambda: importlib.import_module('core.policy_repository'),
    'core.portable_claim_proof': lambda: importlib.import_module('core.portable_claim_proof'),
    'core.principal_seal': lambda: importlib.import_module('core.principal_seal'),
    'core.product_control_plane': lambda: importlib.import_module('core.product_control_plane'),
    'core.product_control_runtime': lambda: importlib.import_module('core.product_control_runtime'),
    'core.product_default_executors': lambda: importlib.import_module('core.product_default_executors'),
    'core.product_executor_registry': lambda: importlib.import_module('core.product_executor_registry'),
    'core.product_kernel': lambda: importlib.import_module('core.product_kernel'),
    'core.product_operations': lambda: importlib.import_module('core.product_operations'),
    'core.product_shell_projection': lambda: importlib.import_module('core.product_shell_projection'),
    'core.progression': lambda: importlib.import_module('core.progression'),
    'core.progression_intelligence': lambda: importlib.import_module('core.progression_intelligence'),
    'core.provenance_ledger': lambda: importlib.import_module('core.provenance_ledger'),
    'core.provider_architecture': lambda: importlib.import_module('core.provider_architecture'),
    'core.quest_graph': lambda: importlib.import_module('core.quest_graph'),
    'core.refine_gates': lambda: importlib.import_module('core.refine_gates'),
    'core.relationship_memory': lambda: importlib.import_module('core.relationship_memory'),
    'core.reliability': lambda: importlib.import_module('core.reliability'),
    'core.render_quality': lambda: importlib.import_module('core.render_quality'),
    'core.reputation': lambda: importlib.import_module('core.reputation'),
    'core.route_islands': lambda: importlib.import_module('core.route_islands'),
    'core.route_policy_catalog': lambda: importlib.import_module('core.route_policy_catalog'),
    'core.route_policy_coverage': lambda: importlib.import_module('core.route_policy_coverage'),
    'core.route_privacy': lambda: importlib.import_module('core.route_privacy'),
    'core.routes_registry': lambda: importlib.import_module('core.routes_registry'),
    'core.runtime_health': lambda: importlib.import_module('core.runtime_health'),
    'core.runtime_resilience': lambda: importlib.import_module('core.runtime_resilience'),
    'core.runtime_sessions': lambda: importlib.import_module('core.runtime_sessions'),
    'core.save_envelope': lambda: importlib.import_module('core.save_envelope'),
    'core.scheduler': lambda: importlib.import_module('core.scheduler'),
    'core.security_config': lambda: importlib.import_module('core.security_config'),
    'core.security_v2': lambda: importlib.import_module('core.security_v2'),
    'core.sensory_cues': lambda: importlib.import_module('core.sensory_cues'),
    'core.settings': lambda: importlib.import_module('core.settings'),
    'core.signed_finality_evidence': lambda: importlib.import_module('core.signed_finality_evidence'),
    'core.signed_portable_claim': lambda: importlib.import_module('core.signed_portable_claim'),
    'core.signed_transparency_witness': lambda: importlib.import_module('core.signed_transparency_witness'),
    'core.skill_graph': lambda: importlib.import_module('core.skill_graph'),
    'core.snowball_axes': lambda: importlib.import_module('core.snowball_axes'),
    'core.snowball_forge': lambda: importlib.import_module('core.snowball_forge'),
    'core.snowball_questionnaire': lambda: importlib.import_module('core.snowball_questionnaire'),
    'core.source_independence': lambda: importlib.import_module('core.source_independence'),
    'core.source_lineage': lambda: importlib.import_module('core.source_lineage'),
    'core.sparse_merkle': lambda: importlib.import_module('core.sparse_merkle'),
    'core.stage_builder': lambda: importlib.import_module('core.stage_builder'),
    'core.stage_vault': lambda: importlib.import_module('core.stage_vault'),
    'core.story_continuity': lambda: importlib.import_module('core.story_continuity'),
    'core.structured_log': lambda: importlib.import_module('core.structured_log'),
    'core.swarm_agents': lambda: importlib.import_module('core.swarm_agents'),
    'core.swarm_planner': lambda: importlib.import_module('core.swarm_planner'),
    'core.swarm_scheduler': lambda: importlib.import_module('core.swarm_scheduler'),
    'core.system_assurance': lambda: importlib.import_module('core.system_assurance'),
    'core.system_root_attestation': lambda: importlib.import_module('core.system_root_attestation'),
    'core.systems_forge': lambda: importlib.import_module('core.systems_forge'),
    'core.systems_forge_ext': lambda: importlib.import_module('core.systems_forge_ext'),
    'core.systems_knowledge': lambda: importlib.import_module('core.systems_knowledge'),
    'core.tenant_storage_boundary': lambda: importlib.import_module('core.tenant_storage_boundary'),
    'core.terrain_field': lambda: importlib.import_module('core.terrain_field'),
    'core.text_gamefile': lambda: importlib.import_module('core.text_gamefile'),
    'core.tool_forge': lambda: importlib.import_module('core.tool_forge'),
    'core.transparency_finality': lambda: importlib.import_module('core.transparency_finality'),
    'core.transparency_finality_proof': lambda: importlib.import_module('core.transparency_finality_proof'),
    'core.transparency_gossip': lambda: importlib.import_module('core.transparency_gossip'),
    'core.transparency_log': lambda: importlib.import_module('core.transparency_log'),
    'core.transparency_witness': lambda: importlib.import_module('core.transparency_witness'),
    'core.transparency_witness_config': lambda: importlib.import_module('core.transparency_witness_config'),
    'core.travel_graph': lambda: importlib.import_module('core.travel_graph'),
    'core.truth_verifier': lambda: importlib.import_module('core.truth_verifier'),
    'core.truth_watch': lambda: importlib.import_module('core.truth_watch'),
    'core.tunnel_watchdog': lambda: importlib.import_module('core.tunnel_watchdog'),
    'core.universal_forge': lambda: importlib.import_module('core.universal_forge'),
    'core.user_control_receipts': lambda: importlib.import_module('core.user_control_receipts'),
    'core.vault_gdd': lambda: importlib.import_module('core.vault_gdd'),
    'core.verified_curiosity': lambda: importlib.import_module('core.verified_curiosity'),
    'core.vfx_combat_catalog': lambda: importlib.import_module('core.vfx_combat_catalog'),
    'core.vfx_cues': lambda: importlib.import_module('core.vfx_cues'),
    'core.voyage_runtime': lambda: importlib.import_module('core.voyage_runtime'),
    'core.whisper_network': lambda: importlib.import_module('core.whisper_network'),
    'core.workspace_projection': lambda: importlib.import_module('core.workspace_projection'),
    'core.world_agents': lambda: importlib.import_module('core.world_agents'),
    'core.world_graph': lambda: importlib.import_module('core.world_graph'),
    'core.world_graph_projection': lambda: importlib.import_module('core.world_graph_projection'),
    'core.world_runtime': lambda: importlib.import_module('core.world_runtime'),
    'core.world_system_composer': lambda: importlib.import_module('core.world_system_composer'),
    'core.worm_audit': lambda: importlib.import_module('core.worm_audit'),
    'seeds.academy_data': lambda: importlib.import_module('seeds.academy_data'),
    'seeds.achievements_mega': lambda: importlib.import_module('seeds.achievements_mega'),
    'seeds.ai_generative_weights_seed': lambda: importlib.import_module('seeds.ai_generative_weights_seed'),
    'seeds.ai_knowledge_vault': lambda: importlib.import_module('seeds.ai_knowledge_vault'),
    'seeds.algo_challenges_data': lambda: importlib.import_module('seeds.algo_challenges_data'),
    'seeds.audio_dsp_seed': lambda: importlib.import_module('seeds.audio_dsp_seed'),
    'seeds.bible_data_expanded': lambda: importlib.import_module('seeds.bible_data_expanded'),
    'seeds.bibles_mega': lambda: importlib.import_module('seeds.bibles_mega'),
    'seeds.bootstrap_seeder': lambda: importlib.import_module('seeds.bootstrap_seeder'),
    'seeds.bugfix_complete': lambda: importlib.import_module('seeds.bugfix_complete'),
    'seeds.bugfix_library': lambda: importlib.import_module('seeds.bugfix_library'),
    'seeds.bugfix_mega': lambda: importlib.import_module('seeds.bugfix_mega'),
    'seeds.build_recipes_seed': lambda: importlib.import_module('seeds.build_recipes_seed'),
    'seeds.challenges_mega': lambda: importlib.import_module('seeds.challenges_mega'),
    'seeds.code_synthesis_seed': lambda: importlib.import_module('seeds.code_synthesis_seed'),
    'seeds.coding_dictionary': lambda: importlib.import_module('seeds.coding_dictionary'),
    'seeds.cognitive_psychographics_seed': lambda: importlib.import_module('seeds.cognitive_psychographics_seed'),
    'seeds.deep_lore_seed': lambda: importlib.import_module('seeds.deep_lore_seed'),
    'seeds.director_pacing_seed': lambda: importlib.import_module('seeds.director_pacing_seed'),
    'seeds.ecosystems_biology_seed': lambda: importlib.import_module('seeds.ecosystems_biology_seed'),
    'seeds.emotional_dialogue_seed': lambda: importlib.import_module('seeds.emotional_dialogue_seed'),
    'seeds.engine_api_seed': lambda: importlib.import_module('seeds.engine_api_seed'),
    'seeds.game_code_library_seed': lambda: importlib.import_module('seeds.game_code_library_seed'),
    'seeds.game_database': lambda: importlib.import_module('seeds.game_database'),
    'seeds.game_design_seed': lambda: importlib.import_module('seeds.game_design_seed'),
    'seeds.gamedev_data': lambda: importlib.import_module('seeds.gamedev_data'),
    'seeds.gamestate_schemas_seed': lambda: importlib.import_module('seeds.gamestate_schemas_seed'),
    'seeds.github_code_seed': lambda: importlib.import_module('seeds.github_code_seed'),
    'seeds.historical_meta_seed': lambda: importlib.import_module('seeds.historical_meta_seed'),
    'seeds.hyperscale_expansion': lambda: importlib.import_module('seeds.hyperscale_expansion'),
    'seeds.hyperscale_micro_dbs': lambda: importlib.import_module('seeds.hyperscale_micro_dbs'),
    'seeds.input_haptics_seed': lambda: importlib.import_module('seeds.input_haptics_seed'),
    'seeds.jeeves_persona_seed': lambda: importlib.import_module('seeds.jeeves_persona_seed'),
    'seeds.knowledge_databases': lambda: importlib.import_module('seeds.knowledge_databases'),
    'seeds.language_classes_seed': lambda: importlib.import_module('seeds.language_classes_seed'),
    'seeds.languages_1000': lambda: importlib.import_module('seeds.languages_1000'),
    'seeds.languages_500': lambda: importlib.import_module('seeds.languages_500'),
    'seeds.leaderboard_data': lambda: importlib.import_module('seeds.leaderboard_data'),
    'seeds.legal_compliance_seed': lambda: importlib.import_module('seeds.legal_compliance_seed'),
    'seeds.library_500': lambda: importlib.import_module('seeds.library_500'),
    'seeds.math_database': lambda: importlib.import_module('seeds.math_database'),
    'seeds.mega_game_db_seed': lambda: importlib.import_module('seeds.mega_game_db_seed'),
    'seeds.mega_generator': lambda: importlib.import_module('seeds.mega_generator'),
    'seeds.open_license_books': lambda: importlib.import_module('seeds.open_license_books'),
    'seeds.patch_notes_extended': lambda: importlib.import_module('seeds.patch_notes_extended'),
    'seeds.patch_notes_seed': lambda: importlib.import_module('seeds.patch_notes_seed'),
    'seeds.phase4_knowledge_seed': lambda: importlib.import_module('seeds.phase4_knowledge_seed'),
    'seeds.physics_materials_seed': lambda: importlib.import_module('seeds.physics_materials_seed'),
    'seeds.procedural_assets_seed': lambda: importlib.import_module('seeds.procedural_assets_seed'),
    'seeds.publishing_assets_seed': lambda: importlib.import_module('seeds.publishing_assets_seed'),
    'seeds.qa_oracles_seed': lambda: importlib.import_module('seeds.qa_oracles_seed'),
    'seeds.reading_content_expansion': lambda: importlib.import_module('seeds.reading_content_expansion'),
    'seeds.reading_content_expansion_v2': lambda: importlib.import_module('seeds.reading_content_expansion_v2'),
    'seeds.reading_content_generator': lambda: importlib.import_module('seeds.reading_content_generator'),
    'seeds.reading_library': lambda: importlib.import_module('seeds.reading_library'),
    'seeds.reading_library_mega': lambda: importlib.import_module('seeds.reading_library_mega'),
    'seeds.reference_encyclopedia': lambda: importlib.import_module('seeds.reference_encyclopedia'),
    'seeds.rosetta_curriculum': lambda: importlib.import_module('seeds.rosetta_curriculum'),
    'seeds.rosetta_expanded': lambda: importlib.import_module('seeds.rosetta_expanded'),
    'seeds.rosetta_expanded_massive': lambda: importlib.import_module('seeds.rosetta_expanded_massive'),
    'seeds.rosetta_expanded_v10': lambda: importlib.import_module('seeds.rosetta_expanded_v10'),
    'seeds.rosetta_expanded_v11': lambda: importlib.import_module('seeds.rosetta_expanded_v11'),
    'seeds.rosetta_expanded_v12': lambda: importlib.import_module('seeds.rosetta_expanded_v12'),
    'seeds.rosetta_expanded_v13': lambda: importlib.import_module('seeds.rosetta_expanded_v13'),
    'seeds.rosetta_expanded_v14': lambda: importlib.import_module('seeds.rosetta_expanded_v14'),
    'seeds.rosetta_expanded_v15': lambda: importlib.import_module('seeds.rosetta_expanded_v15'),
    'seeds.rosetta_expanded_v16_18': lambda: importlib.import_module('seeds.rosetta_expanded_v16_18'),
    'seeds.rosetta_expanded_v19_22': lambda: importlib.import_module('seeds.rosetta_expanded_v19_22'),
    'seeds.rosetta_expanded_v2': lambda: importlib.import_module('seeds.rosetta_expanded_v2'),
    'seeds.rosetta_expanded_v23_26': lambda: importlib.import_module('seeds.rosetta_expanded_v23_26'),
    'seeds.rosetta_expanded_v27_32': lambda: importlib.import_module('seeds.rosetta_expanded_v27_32'),
    'seeds.rosetta_expanded_v3': lambda: importlib.import_module('seeds.rosetta_expanded_v3'),
    'seeds.rosetta_expanded_v33_36': lambda: importlib.import_module('seeds.rosetta_expanded_v33_36'),
    'seeds.rosetta_expanded_v37_40': lambda: importlib.import_module('seeds.rosetta_expanded_v37_40'),
    'seeds.rosetta_expanded_v4': lambda: importlib.import_module('seeds.rosetta_expanded_v4'),
    'seeds.rosetta_expanded_v41_45': lambda: importlib.import_module('seeds.rosetta_expanded_v41_45'),
    'seeds.rosetta_expanded_v46_50': lambda: importlib.import_module('seeds.rosetta_expanded_v46_50'),
    'seeds.rosetta_expanded_v5': lambda: importlib.import_module('seeds.rosetta_expanded_v5'),
    'seeds.rosetta_expanded_v51_55': lambda: importlib.import_module('seeds.rosetta_expanded_v51_55'),
    'seeds.rosetta_expanded_v56_60': lambda: importlib.import_module('seeds.rosetta_expanded_v56_60'),
    'seeds.rosetta_expanded_v6': lambda: importlib.import_module('seeds.rosetta_expanded_v6'),
    'seeds.rosetta_expanded_v61_65': lambda: importlib.import_module('seeds.rosetta_expanded_v61_65'),
    'seeds.rosetta_expanded_v66_70': lambda: importlib.import_module('seeds.rosetta_expanded_v66_70'),
    'seeds.rosetta_expanded_v7': lambda: importlib.import_module('seeds.rosetta_expanded_v7'),
    'seeds.rosetta_expanded_v71_75': lambda: importlib.import_module('seeds.rosetta_expanded_v71_75'),
    'seeds.rosetta_expanded_v76_80': lambda: importlib.import_module('seeds.rosetta_expanded_v76_80'),
    'seeds.rosetta_expanded_v8': lambda: importlib.import_module('seeds.rosetta_expanded_v8'),
    'seeds.rosetta_expanded_v81_85': lambda: importlib.import_module('seeds.rosetta_expanded_v81_85'),
    'seeds.rosetta_expanded_v86_90': lambda: importlib.import_module('seeds.rosetta_expanded_v86_90'),
    'seeds.rosetta_expanded_v9': lambda: importlib.import_module('seeds.rosetta_expanded_v9'),
    'seeds.rosetta_expanded_v91_94': lambda: importlib.import_module('seeds.rosetta_expanded_v91_94'),
    'seeds.rosetta_expanded_v95_100': lambda: importlib.import_module('seeds.rosetta_expanded_v95_100'),
    'seeds.rosetta_stone_seed': lambda: importlib.import_module('seeds.rosetta_stone_seed'),
    'seeds.rosetta_true': lambda: importlib.import_module('seeds.rosetta_true'),
    'seeds.rosetta_ultimo': lambda: importlib.import_module('seeds.rosetta_ultimo'),
    'seeds.security_crypto_seed': lambda: importlib.import_module('seeds.security_crypto_seed'),
    'seeds.seed_runner': lambda: importlib.import_module('seeds.seed_runner'),
    'seeds.study_paths': lambda: importlib.import_module('seeds.study_paths'),
    'seeds.tracks_20k': lambda: importlib.import_module('seeds.tracks_20k'),
    'seeds.tracks_expansion': lambda: importlib.import_module('seeds.tracks_expansion'),
    'seeds.unique_flair_seed': lambda: importlib.import_module('seeds.unique_flair_seed'),
    'seeds.variation_mutation_seed': lambda: importlib.import_module('seeds.variation_mutation_seed'),
    'seeds.vault_architecture': lambda: importlib.import_module('seeds.vault_architecture'),
    'seeds.vault_final': lambda: importlib.import_module('seeds.vault_final'),
    'seeds.vault_frameworks': lambda: importlib.import_module('seeds.vault_frameworks'),
    'seeds.vault_languages': lambda: importlib.import_module('seeds.vault_languages'),
    'seeds.vault_mega': lambda: importlib.import_module('seeds.vault_mega'),
    'seeds.vault_ml_data': lambda: importlib.import_module('seeds.vault_ml_data'),
    'seeds.visual_juice_seed': lambda: importlib.import_module('seeds.visual_juice_seed'),
}


class _LazyModule:
    """Defer execution while retaining Python's normal import locking/cache."""

    __slots__ = ("_module_name", "_loader")

    def __init__(self, module_name: str, loader):
        self._module_name = module_name
        self._loader = loader

    def __getattr__(self, name: str):
        return getattr(self._loader(), name)

    def __repr__(self):
        return f"<lazy module {self._module_name!r}>"


def lazy_import(module_name: str):
    """Defer one repository-owned literal loader without changing sys.modules."""
    if not isinstance(module_name, str) or module_name not in _LOADERS:
        raise ValueError("module is not registered for deferred loading")
    return _LazyModule(module_name, _LOADERS[module_name])

_proxies: dict = {}
_DIR = pathlib.Path(__file__).resolve().parent
# Modules that must NOT be lazily proxied (this module, and ultra-hot tiny ones
# that are always needed at import time anyway).
_SKIP = {"lazy_registry", "unbulk", "databases"}


def __getattr__(name: str):  # PEP 562 — lazy attribute access on the module
    if name.startswith("_") or name in _SKIP or f"core.{name}" not in _LOADERS:
        raise AttributeError(f"module 'core.lazy_registry' has no attribute '{name}'")
    if name not in _proxies:
        _proxies[name] = lazy_import(f"core.{name}")
    return _proxies[name]


def module_names() -> list[str]:
    """Every importable core module (sans the skip list)."""
    return sorted(
        f.stem for f in _DIR.glob("*.py")
        if not f.stem.startswith("_") and f.stem not in _SKIP
    )


def wrap_all() -> dict:
    """Return {module_name: lazy_proxy} for EVERY core module — wrap them all."""
    for n in module_names():
        if n not in _proxies:
            _proxies[n] = lazy_import(f"core.{n}")
    return dict(_proxies)


def status() -> dict:
    """Introspection: which core modules are deferred vs already loaded."""
    names = module_names()
    loaded = [n for n in names if f"core.{n}" in sys.modules]
    return {
        "total": len(names),
        "loaded": len(loaded),
        "deferred": len(names) - len(loaded),
        "wrapped_proxies": len(_proxies),
        "loaded_modules": loaded,
    }


# ── NON-CORE packages (seeds / routes) — lazy-wrapped the same way ───────────
_NONCORE = ("seeds",)            # routes must be eager (FastAPI registers them)
_noncore_proxies: dict = {}
_ROOT = _DIR.parent


def _pkg_module_names(pkg: str) -> list[str]:
    d = _ROOT / pkg
    if not d.exists():
        return []
    return sorted(f.stem for f in d.glob("*.py") if not f.stem.startswith("_"))


def seed(name: str):
    """Lazy proxy for a `seeds.<name>` module (imported on first use)."""
    key = f"seeds.{name}"
    if key not in _noncore_proxies:
        _noncore_proxies[key] = lazy_import(key)
    return _noncore_proxies[key]


def wrap_noncore() -> dict:
    """Wrap every non-core (seeds) module as a lazy proxy."""
    for pkg in _NONCORE:
        for n in _pkg_module_names(pkg):
            key = f"{pkg}.{n}"
            if key not in _noncore_proxies:
                _noncore_proxies[key] = lazy_import(key)
    return dict(_noncore_proxies)


def wrap_flagged() -> dict:
    """Wrap exactly the FLAGGED heavy modules (unbulk.lazy_eligible) as lazy
    proxies — the big seed data that should never sit on the import path."""
    from core import unbulk
    inv = unbulk.module_inventory(top=10_000)
    out = {}
    for m in inv["biggest"]:
        if not m.get("lazy_eligible"):
            continue
        mod = m["module"].replace("/", ".").removesuffix(".py")  # seeds/x.py → seeds.x
        if mod not in _noncore_proxies:
            _noncore_proxies[mod] = lazy_import(mod)
        out[mod] = _noncore_proxies[mod]
    return out


def full_status() -> dict:
    """Combined loaded-vs-deferred picture across core + seeds + flagged."""
    core_names = module_names()
    seed_names = [f"seeds.{n}" for n in _pkg_module_names("seeds")]
    from core import unbulk
    flagged = [m["module"].replace("/", ".").removesuffix(".py")
               for m in unbulk.module_inventory(top=10_000)["biggest"]
               if m.get("lazy_eligible")]
    def _split(keys, pfx_core=False):
        ld = [k for k in keys if (f"core.{k}" if pfx_core else k) in sys.modules]
        return len(keys), len(ld), [k for k in keys if (f"core.{k}" if pfx_core else k) not in sys.modules]
    c_t, c_l, c_def = _split(core_names, pfx_core=True)
    s_t, s_l, s_def = _split(seed_names)
    f_t, f_l, f_def = _split(flagged)
    return {
        "core": {"total": c_t, "loaded": c_l, "deferred": c_t - c_l},
        "seeds": {"total": s_t, "loaded": s_l, "deferred": s_t - s_l, "deferred_modules": s_def},
        "flagged": {"total": f_t, "loaded": f_l, "deferred": f_t - f_l,
                    "modules": flagged, "still_deferred": f_def},
        "wrapped_proxies": {"core": len(_proxies), "noncore": len(_noncore_proxies)},
    }
