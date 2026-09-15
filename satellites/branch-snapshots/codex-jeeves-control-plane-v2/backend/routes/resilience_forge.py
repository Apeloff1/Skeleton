"""
╔══════════════════════════════════════════════════════════════════════════════════╗
║           RESILIENCE FORGE v1.0 — 8 SUBSYSTEM CITADEL                          ║
║                                                                                  ║
║  ResilienceRoot   • DuplicateDome  • MirrorMesh  • CrashCradle                 ║
║  BackupBeacon     • StateShadow    • FailoverForge • GraceGuard                ║
║                                                                                  ║
║  Every subsystem tracks:                                                         ║
║    • Operational status (active/degraded/critical/offline)                       ║
║    • Health score (0-100)                                                        ║
║    • Events processed / errors caught / recoveries made                          ║
║    • Intricate internal metrics unique to each subsystem                          ║
║    • Cross-system dependency graph (which systems feed into which)               ║
║    • Failover chains, mirror integrity, crash recovery analytics                 ║
╚══════════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from datetime import datetime
import random, hashlib, time
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/api/resilience-forge", tags=["resilience-forge"])

# ─── SUBSYSTEM ENGINE ────────────────────────────────────────────────────────

def _seed_rng(subsystem: str, seed_extra: str = ""):
    """Deterministic RNG for consistent demo data per 30-second window."""
    t = int(time.time() // 30)
    seed = int(hashlib.md5(f"rf:{subsystem}:{seed_extra}:{t}".encode()).hexdigest()[:8], 16)
    random.seed(seed)


class ForgeSubsystems:
    """Generates intricate state for each Resilience Forge subsystem."""

    # ═══════════════════════════════════════════════════════════════════════
    # 1. RESILIENCE ROOT — Foundation layer: heartbeat, liveness, readiness
    # ═══════════════════════════════════════════════════════════════════════
    @staticmethod
    def resilience_root() -> dict:
        _seed_rng("resilience_root")
        heartbeat_interval_ms = random.randint(500, 3000)
        missed_heartbeats = random.randint(0, 5)
        liveness_checks_passed = random.randint(900, 1000)
        liveness_checks_failed = random.randint(0, 8)
        readiness_score = round(random.uniform(70, 100), 1)
        circuit_state = random.choice(["closed", "closed", "closed", "half-open", "open"])
        uptime_sec = random.randint(3600, 864000)
        restart_count = random.randint(0, 3)
        watchdog_triggers = random.randint(0, 7)
        deep_health_score = round(random.uniform(60, 100), 1)
        dependency_chain_depth = random.randint(3, 12)
        cascading_failure_risk = round(random.uniform(0, 30), 1)
        self_heal_attempts = random.randint(0, 15)
        self_heal_success = random.randint(0, self_heal_attempts) if self_heal_attempts > 0 else 0
        entropy_index = round(random.uniform(0.01, 0.35), 3)

        health = round(max(0, readiness_score - missed_heartbeats * 4 - liveness_checks_failed * 2 - (10 if circuit_state == "open" else 0)), 1)

        return {
            "id": "resilience_root", "name": "ResilienceRoot", "icon": "git-branch",
            "status": "critical" if circuit_state == "open" else "degraded" if missed_heartbeats > 3 else "active",
            "health": health,
            "color": "#EF4444" if health < 50 else "#F97316" if health < 75 else "#22C55E",
            "metrics": {
                "heartbeat_interval_ms": heartbeat_interval_ms,
                "missed_heartbeats": missed_heartbeats,
                "liveness_checks_passed": liveness_checks_passed,
                "liveness_checks_failed": liveness_checks_failed,
                "readiness_score": readiness_score,
                "circuit_breaker_state": circuit_state,
                "uptime_seconds": uptime_sec,
                "restart_count": restart_count,
                "watchdog_triggers": watchdog_triggers,
                "deep_health_score": deep_health_score,
                "dependency_chain_depth": dependency_chain_depth,
                "cascading_failure_risk_pct": cascading_failure_risk,
                "self_heal_attempts": self_heal_attempts,
                "self_heal_success": self_heal_success,
                "self_heal_rate_pct": round(self_heal_success / max(self_heal_attempts, 1) * 100, 1),
                "entropy_index": entropy_index,
                "root_anchor_epoch": int(time.time()) - uptime_sec,
                "probes_active": random.randint(3, 12),
            },
            "root_protocols": {
                "auto_restart_on_failure": True,
                "cascading_failure_breaker": True,
                "exponential_backoff_restart": True,
                "watchdog_enabled": True,
                "self_heal_enabled": True,
                "deep_health_probe_interval_sec": 30,
                "heartbeat_timeout_ms": heartbeat_interval_ms * 3,
                "max_restart_attempts": 5,
            },
            "events_processed": random.randint(8000, 50000),
            "last_event": datetime.utcnow().isoformat(),
        }

    # ═══════════════════════════════════════════════════════════════════════
    # 2. DUPLICATE DOME — Data replication & redundancy layer
    # ═══════════════════════════════════════════════════════════════════════
    @staticmethod
    def duplicate_dome() -> dict:
        _seed_rng("duplicate_dome")
        replicas = random.randint(2, 5)
        sync_lag_ms = round(random.uniform(0, 150), 1)
        replication_factor = replicas
        conflict_count = random.randint(0, 8)
        conflict_resolved = random.randint(0, conflict_count)
        data_integrity_pct = round(random.uniform(95, 100), 2)
        last_snapshot_age_sec = random.randint(5, 600)
        snapshot_size_mb = round(random.uniform(0.5, 50), 1)
        write_amplification = round(random.uniform(1.0, 3.5), 2)
        compaction_pending = random.randint(0, 5)
        wal_size_mb = round(random.uniform(0.1, 10), 2)
        tombstone_count = random.randint(0, 200)
        anti_entropy_repairs = random.randint(0, 20)
        quorum_size = max(1, replicas // 2 + 1)
        consistency_level = random.choice(["strong", "strong", "eventual", "read-your-writes"])
        read_repair_count = random.randint(0, 30)

        health = round(max(0, data_integrity_pct - (conflict_count - conflict_resolved) * 5 - sync_lag_ms * 0.1), 1)

        return {
            "id": "duplicate_dome", "name": "DuplicateDome", "icon": "copy",
            "status": "critical" if data_integrity_pct < 97 else "degraded" if sync_lag_ms > 80 else "active",
            "health": health,
            "color": "#EF4444" if health < 60 else "#F97316" if health < 80 else "#22C55E",
            "metrics": {
                "active_replicas": replicas,
                "replication_factor": replication_factor,
                "sync_lag_ms": sync_lag_ms,
                "conflict_count": conflict_count,
                "conflicts_resolved": conflict_resolved,
                "conflicts_pending": conflict_count - conflict_resolved,
                "data_integrity_pct": data_integrity_pct,
                "last_snapshot_age_sec": last_snapshot_age_sec,
                "snapshot_size_mb": snapshot_size_mb,
                "write_amplification_factor": write_amplification,
                "compaction_pending": compaction_pending,
                "wal_size_mb": wal_size_mb,
                "tombstone_count": tombstone_count,
                "anti_entropy_repairs": anti_entropy_repairs,
                "quorum_size": quorum_size,
                "consistency_level": consistency_level,
                "read_repair_count": read_repair_count,
                "merkle_tree_depth": random.randint(8, 16),
            },
            "dome_protocols": {
                "multi_master_replication": True,
                "conflict_resolution_strategy": "last-write-wins",
                "auto_compaction": True,
                "snapshot_interval_sec": 300,
                "anti_entropy_enabled": True,
                "read_repair_enabled": True,
                "wal_flush_interval_ms": 100,
                "tombstone_gc_grace_sec": 86400,
            },
            "events_processed": random.randint(5000, 35000),
            "last_event": datetime.utcnow().isoformat(),
        }

    # ═══════════════════════════════════════════════════════════════════════
    # 3. MIRROR MESH — State mirroring across execution contexts
    # ═══════════════════════════════════════════════════════════════════════
    @staticmethod
    def mirror_mesh() -> dict:
        _seed_rng("mirror_mesh")
        mesh_nodes = random.randint(3, 8)
        active_mirrors = random.randint(2, mesh_nodes)
        stale_mirrors = mesh_nodes - active_mirrors
        sync_round_trip_ms = round(random.uniform(5, 80), 1)
        divergence_events = random.randint(0, 12)
        auto_reconciled = random.randint(0, divergence_events)
        mirror_fidelity_pct = round(random.uniform(90, 100), 2)
        bandwidth_used_kbps = random.randint(10, 5000)
        vector_clock_drift = random.randint(0, 5)
        gossip_rounds = random.randint(100, 5000)
        partition_detections = random.randint(0, 3)
        split_brain_avoided = random.randint(0, partition_detections)
        crdt_merges = random.randint(50, 2000)
        lamport_timestamp = random.randint(100000, 999999)

        health = round(max(0, mirror_fidelity_pct - stale_mirrors * 5 - divergence_events * 2 - partition_detections * 8), 1)

        return {
            "id": "mirror_mesh", "name": "MirrorMesh", "icon": "git-compare",
            "status": "critical" if partition_detections > 1 else "degraded" if stale_mirrors > 2 else "active",
            "health": health,
            "color": "#EF4444" if health < 55 else "#F97316" if health < 78 else "#22C55E",
            "metrics": {
                "mesh_nodes": mesh_nodes,
                "active_mirrors": active_mirrors,
                "stale_mirrors": stale_mirrors,
                "sync_round_trip_ms": sync_round_trip_ms,
                "divergence_events": divergence_events,
                "auto_reconciled": auto_reconciled,
                "unreconciled": divergence_events - auto_reconciled,
                "mirror_fidelity_pct": mirror_fidelity_pct,
                "bandwidth_used_kbps": bandwidth_used_kbps,
                "vector_clock_drift": vector_clock_drift,
                "gossip_rounds_completed": gossip_rounds,
                "partition_detections": partition_detections,
                "split_brain_avoided": split_brain_avoided,
                "crdt_merges": crdt_merges,
                "lamport_timestamp": lamport_timestamp,
                "topology": random.choice(["full-mesh", "ring", "star", "hybrid"]),
                "encryption_in_transit": True,
            },
            "mesh_protocols": {
                "crdt_conflict_resolution": True,
                "gossip_protocol_enabled": True,
                "vector_clock_sync": True,
                "partition_detection": True,
                "split_brain_prevention": True,
                "adaptive_sync_interval": True,
                "bandwidth_throttle_kbps": 10000,
                "max_divergence_tolerance": 5,
            },
            "events_processed": random.randint(10000, 60000),
            "last_event": datetime.utcnow().isoformat(),
        }

    # ═══════════════════════════════════════════════════════════════════════
    # 4. CRASH CRADLE — Crash capture, soft-landing, recovery orchestration
    # ═══════════════════════════════════════════════════════════════════════
    @staticmethod
    def crash_cradle() -> dict:
        _seed_rng("crash_cradle")
        total_crashes = random.randint(0, 15)
        soft_landed = random.randint(0, total_crashes)
        hard_crashes = total_crashes - soft_landed
        crash_reports_captured = random.randint(0, total_crashes)
        symbolication_rate_pct = round(random.uniform(80, 100), 1) if crash_reports_captured > 0 else 100
        recovery_time_avg_ms = round(random.uniform(100, 5000), 0) if total_crashes > 0 else 0
        state_snapshots_saved = random.randint(5, 100)
        checkpoint_interval_sec = random.randint(10, 120)
        rollback_count = random.randint(0, 5)
        last_crash_ago_sec = random.randint(300, 86400) if total_crashes > 0 else -1
        crash_free_rate_pct = round(random.uniform(92, 100), 2)
        breadcrumb_trail_depth = random.randint(20, 200)
        oom_kills = random.randint(0, 3)
        anr_count = random.randint(0, 5)
        signal_catches = {"SIGTERM": random.randint(0, 5), "SIGABRT": random.randint(0, 2), "SIGSEGV": random.randint(0, 1)}
        graceful_shutdowns = random.randint(5, 50)

        health = round(max(0, crash_free_rate_pct - hard_crashes * 5 - oom_kills * 8 - anr_count * 3), 1)

        return {
            "id": "crash_cradle", "name": "CrashCradle", "icon": "umbrella",
            "status": "critical" if hard_crashes > 5 else "degraded" if total_crashes > 8 else "active",
            "health": health,
            "color": "#EF4444" if health < 50 else "#F97316" if health < 75 else "#22C55E",
            "metrics": {
                "total_crashes": total_crashes,
                "soft_landed": soft_landed,
                "hard_crashes": hard_crashes,
                "crash_reports_captured": crash_reports_captured,
                "symbolication_rate_pct": symbolication_rate_pct,
                "recovery_time_avg_ms": recovery_time_avg_ms,
                "state_snapshots_saved": state_snapshots_saved,
                "checkpoint_interval_sec": checkpoint_interval_sec,
                "rollback_count": rollback_count,
                "last_crash_ago_sec": last_crash_ago_sec,
                "crash_free_rate_pct": crash_free_rate_pct,
                "breadcrumb_trail_depth": breadcrumb_trail_depth,
                "oom_kills": oom_kills,
                "anr_count": anr_count,
                "signal_catches": signal_catches,
                "graceful_shutdowns": graceful_shutdowns,
                "crash_loop_detection": total_crashes > 3 and last_crash_ago_sec < 600 if total_crashes > 0 else False,
                "last_good_state_age_sec": random.randint(10, 300),
            },
            "cradle_protocols": {
                "soft_landing_enabled": True,
                "auto_state_snapshot": True,
                "breadcrumb_tracking": True,
                "crash_loop_breaker": True,
                "oom_preemptive_gc": True,
                "anr_watchdog_ms": 5000,
                "checkpoint_on_background": True,
                "signal_handler_installed": True,
                "symbolication_on_capture": True,
                "max_crash_reports_stored": 50,
            },
            "events_processed": random.randint(2000, 20000),
            "last_event": datetime.utcnow().isoformat(),
        }

    # ═══════════════════════════════════════════════════════════════════════
    # 5. BACKUP BEACON — Persistent backup signals, recovery points
    # ═══════════════════════════════════════════════════════════════════════
    @staticmethod
    def backup_beacon() -> dict:
        _seed_rng("backup_beacon")
        total_backups = random.randint(10, 200)
        successful_backups = random.randint(int(total_backups * 0.9), total_backups)
        failed_backups = total_backups - successful_backups
        backup_size_total_mb = round(random.uniform(5, 500), 1)
        last_backup_age_sec = random.randint(30, 3600)
        backup_frequency_sec = random.randint(60, 1800)
        restore_test_count = random.randint(0, 20)
        restore_success_pct = round(random.uniform(90, 100), 1) if restore_test_count > 0 else 100
        incremental_ratio = round(random.uniform(0.6, 0.95), 2)
        retention_policy_days = random.choice([7, 14, 30, 90])
        encryption_enabled = True
        compression_ratio = round(random.uniform(0.3, 0.7), 2)
        beacon_signal_strength = round(random.uniform(70, 100), 1)
        recovery_point_objective_sec = random.randint(60, 600)
        recovery_time_objective_sec = random.randint(30, 300)
        offsite_replicas = random.randint(0, 3)
        verification_hash_matches = random.randint(50, 500)
        verification_hash_failures = random.randint(0, 3)

        health = round(max(0, beacon_signal_strength - failed_backups * 5 - verification_hash_failures * 10), 1)

        return {
            "id": "backup_beacon", "name": "BackupBeacon", "icon": "cloud-upload",
            "status": "critical" if failed_backups > 5 else "degraded" if last_backup_age_sec > 1800 else "active",
            "health": health,
            "color": "#EF4444" if health < 55 else "#F97316" if health < 78 else "#22C55E",
            "metrics": {
                "total_backups": total_backups,
                "successful_backups": successful_backups,
                "failed_backups": failed_backups,
                "backup_size_total_mb": backup_size_total_mb,
                "last_backup_age_sec": last_backup_age_sec,
                "backup_frequency_sec": backup_frequency_sec,
                "restore_tests_run": restore_test_count,
                "restore_success_pct": restore_success_pct,
                "incremental_ratio": incremental_ratio,
                "retention_policy_days": retention_policy_days,
                "compression_ratio": compression_ratio,
                "beacon_signal_strength_pct": beacon_signal_strength,
                "rpo_sec": recovery_point_objective_sec,
                "rto_sec": recovery_time_objective_sec,
                "offsite_replicas": offsite_replicas,
                "verification_hash_matches": verification_hash_matches,
                "verification_hash_failures": verification_hash_failures,
                "deduplication_savings_pct": round(random.uniform(10, 60), 1),
            },
            "beacon_protocols": {
                "auto_backup_enabled": True,
                "incremental_backup": True,
                "encryption_at_rest": encryption_enabled,
                "compression_enabled": True,
                "offsite_replication": offsite_replicas > 0,
                "verification_on_write": True,
                "restore_test_schedule": "weekly",
                "retention_auto_cleanup": True,
                "deduplication_enabled": True,
                "point_in_time_recovery": True,
            },
            "events_processed": random.randint(3000, 25000),
            "last_event": datetime.utcnow().isoformat(),
        }

    # ═══════════════════════════════════════════════════════════════════════
    # 6. STATE SHADOW — Shadow state tracking, diff engine, rollback
    # ═══════════════════════════════════════════════════════════════════════
    @staticmethod
    def state_shadow() -> dict:
        _seed_rng("state_shadow")
        shadow_copies_active = random.randint(3, 15)
        state_diffs_computed = random.randint(200, 10000)
        diff_avg_size_bytes = random.randint(50, 5000)
        rollback_available = random.randint(5, 50)
        rollbacks_executed = random.randint(0, 10)
        rollback_success_pct = round(random.uniform(90, 100), 1) if rollbacks_executed > 0 else 100
        snapshot_frequency_ms = random.randint(500, 5000)
        shadow_lag_ms = round(random.uniform(1, 50), 1)
        mutation_tracking_depth = random.randint(3, 20)
        patches_applied = random.randint(100, 5000)
        patches_rejected = random.randint(0, 20)
        immutable_violations_caught = random.randint(0, 15)
        time_travel_checkpoints = random.randint(10, 100)
        structural_sharing_pct = round(random.uniform(50, 95), 1)
        shadow_memory_mb = round(random.uniform(1, 30), 1)
        proxy_trap_count = random.randint(500, 20000)

        health = round(max(0, 100 - shadow_lag_ms * 0.5 - patches_rejected * 2 - immutable_violations_caught * 3), 1)

        return {
            "id": "state_shadow", "name": "StateShadow", "icon": "eye-off",
            "status": "degraded" if immutable_violations_caught > 5 else "active",
            "health": health,
            "color": "#F97316" if health < 70 else "#22C55E",
            "metrics": {
                "shadow_copies_active": shadow_copies_active,
                "state_diffs_computed": state_diffs_computed,
                "diff_avg_size_bytes": diff_avg_size_bytes,
                "rollback_points_available": rollback_available,
                "rollbacks_executed": rollbacks_executed,
                "rollback_success_pct": rollback_success_pct,
                "snapshot_frequency_ms": snapshot_frequency_ms,
                "shadow_lag_ms": shadow_lag_ms,
                "mutation_tracking_depth": mutation_tracking_depth,
                "patches_applied": patches_applied,
                "patches_rejected": patches_rejected,
                "immutable_violations_caught": immutable_violations_caught,
                "time_travel_checkpoints": time_travel_checkpoints,
                "structural_sharing_pct": structural_sharing_pct,
                "shadow_memory_mb": shadow_memory_mb,
                "proxy_trap_count": proxy_trap_count,
                "diff_algorithm": random.choice(["myers", "patience", "histogram"]),
            },
            "shadow_protocols": {
                "immutability_enforcement": True,
                "structural_sharing": True,
                "lazy_diff_computation": True,
                "time_travel_enabled": True,
                "proxy_based_tracking": True,
                "auto_snapshot_on_mutation": True,
                "rollback_undo_stack_size": 50,
                "diff_compression": True,
                "patch_validation": True,
                "shadow_gc_interval_sec": 60,
            },
            "events_processed": random.randint(15000, 80000),
            "last_event": datetime.utcnow().isoformat(),
        }

    # ═══════════════════════════════════════════════════════════════════════
    # 7. FAILOVER FORGE — Hot/warm/cold failover orchestration
    # ═══════════════════════════════════════════════════════════════════════
    @staticmethod
    def failover_forge() -> dict:
        _seed_rng("failover_forge")
        primary_health = round(random.uniform(50, 100), 1)
        standby_count = random.randint(1, 4)
        hot_standbys = random.randint(0, min(2, standby_count))
        warm_standbys = standby_count - hot_standbys
        failover_events = random.randint(0, 8)
        failover_success = random.randint(0, failover_events) if failover_events > 0 else 0
        failover_time_avg_ms = round(random.uniform(50, 3000), 0) if failover_events > 0 else 0
        split_brain_events = random.randint(0, 2)
        leader_election_rounds = random.randint(0, 10)
        heartbeat_latency_ms = round(random.uniform(5, 100), 1)
        promotion_queue_depth = random.randint(0, 3)
        demotion_events = random.randint(0, 3)
        fencing_tokens_issued = random.randint(0, 20)
        consensus_algorithm = random.choice(["raft", "paxos", "zab", "viewstamped"])
        quorum_met = random.random() > 0.05
        last_failover_ago_sec = random.randint(600, 86400) if failover_events > 0 else -1
        data_loss_events = random.randint(0, 1)

        health = round(max(0, primary_health - split_brain_events * 15 - data_loss_events * 25 - (failover_events - failover_success) * 8), 1)

        return {
            "id": "failover_forge", "name": "FailoverForge", "icon": "swap-horizontal",
            "status": "critical" if split_brain_events > 0 or data_loss_events > 0 else "degraded" if not quorum_met else "active",
            "health": health,
            "color": "#EF4444" if health < 50 else "#F97316" if health < 75 else "#22C55E",
            "metrics": {
                "primary_health_pct": primary_health,
                "standby_count": standby_count,
                "hot_standbys": hot_standbys,
                "warm_standbys": warm_standbys,
                "failover_events": failover_events,
                "failover_success": failover_success,
                "failover_success_rate_pct": round(failover_success / max(failover_events, 1) * 100, 1),
                "failover_time_avg_ms": failover_time_avg_ms,
                "split_brain_events": split_brain_events,
                "leader_election_rounds": leader_election_rounds,
                "heartbeat_latency_ms": heartbeat_latency_ms,
                "promotion_queue_depth": promotion_queue_depth,
                "demotion_events": demotion_events,
                "fencing_tokens_issued": fencing_tokens_issued,
                "consensus_algorithm": consensus_algorithm,
                "quorum_met": quorum_met,
                "last_failover_ago_sec": last_failover_ago_sec,
                "data_loss_events": data_loss_events,
            },
            "forge_protocols": {
                "automatic_failover": True,
                "fencing_enabled": True,
                "split_brain_prevention": True,
                "leader_election_enabled": True,
                "hot_standby_replication": hot_standbys > 0,
                "warm_standby_catchup": warm_standbys > 0,
                "failover_timeout_ms": 5000,
                "promotion_priority_list": True,
                "data_loss_prevention_mode": "synchronous",
                "health_check_interval_ms": 1000,
            },
            "events_processed": random.randint(5000, 40000),
            "last_event": datetime.utcnow().isoformat(),
        }

    # ═══════════════════════════════════════════════════════════════════════
    # 8. GRACE GUARD — Graceful degradation, feature flags, load shedding
    # ═══════════════════════════════════════════════════════════════════════
    @staticmethod
    def grace_guard() -> dict:
        _seed_rng("grace_guard")
        feature_flags_total = random.randint(20, 80)
        feature_flags_active = random.randint(15, feature_flags_total)
        feature_flags_degraded = random.randint(0, 10)
        load_shedding_active = random.random() > 0.7
        load_shed_pct = round(random.uniform(0, 40), 1) if load_shedding_active else 0
        requests_shed = random.randint(0, 500) if load_shedding_active else 0
        graceful_fallbacks_triggered = random.randint(0, 30)
        ux_impact_score = round(random.uniform(85, 100), 1) if not load_shedding_active else round(random.uniform(60, 90), 1)
        circuit_breakers_open = random.randint(0, 3)
        bulkhead_partitions = random.randint(3, 10)
        timeout_adaptations = random.randint(0, 50)
        retry_budget_remaining_pct = round(random.uniform(30, 100), 1)
        priority_queue_depth = random.randint(0, 15)
        critical_path_protected = True
        non_critical_paused = random.randint(0, 8)
        degradation_level = "none" if not load_shedding_active else "light" if load_shed_pct < 15 else "moderate" if load_shed_pct < 30 else "heavy"
        user_notifications_sent = random.randint(0, 5) if load_shedding_active else 0

        health = round(max(0, ux_impact_score - circuit_breakers_open * 8 - load_shed_pct * 0.3 - feature_flags_degraded * 2), 1)

        return {
            "id": "grace_guard", "name": "GraceGuard", "icon": "flower",
            "status": "critical" if circuit_breakers_open > 2 else "degraded" if load_shedding_active else "active",
            "health": health,
            "color": "#EF4444" if health < 55 else "#F97316" if health < 78 else "#22C55E",
            "metrics": {
                "feature_flags_total": feature_flags_total,
                "feature_flags_active": feature_flags_active,
                "feature_flags_degraded": feature_flags_degraded,
                "load_shedding_active": load_shedding_active,
                "load_shed_pct": load_shed_pct,
                "requests_shed": requests_shed,
                "graceful_fallbacks_triggered": graceful_fallbacks_triggered,
                "ux_impact_score": ux_impact_score,
                "circuit_breakers_open": circuit_breakers_open,
                "bulkhead_partitions": bulkhead_partitions,
                "timeout_adaptations": timeout_adaptations,
                "retry_budget_remaining_pct": retry_budget_remaining_pct,
                "priority_queue_depth": priority_queue_depth,
                "non_critical_features_paused": non_critical_paused,
                "degradation_level": degradation_level,
                "user_notifications_sent": user_notifications_sent,
                "critical_path_latency_ms": round(random.uniform(10, 100), 1),
            },
            "guard_protocols": {
                "progressive_degradation": True,
                "feature_flag_kill_switch": True,
                "load_shedding_enabled": True,
                "circuit_breaker_pattern": True,
                "bulkhead_isolation": True,
                "adaptive_timeouts": True,
                "retry_budget_enforcement": True,
                "priority_request_routing": True,
                "user_notification_on_degrade": True,
                "auto_recovery_on_healthy": True,
            },
            "events_processed": random.randint(8000, 45000),
            "last_event": datetime.utcnow().isoformat(),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# DEPENDENCY GRAPH — Cross-system relationships
# ═══════════════════════════════════════════════════════════════════════════════

FORGE_DEPENDENCY_GRAPH = {
    "resilience_root":  {"feeds": ["failover_forge", "crash_cradle", "grace_guard"], "consumes": []},
    "duplicate_dome":   {"feeds": ["mirror_mesh", "backup_beacon"], "consumes": ["resilience_root"]},
    "mirror_mesh":      {"feeds": ["state_shadow"], "consumes": ["duplicate_dome", "failover_forge"]},
    "crash_cradle":     {"feeds": ["backup_beacon", "state_shadow"], "consumes": ["resilience_root", "grace_guard"]},
    "backup_beacon":    {"feeds": [], "consumes": ["duplicate_dome", "crash_cradle", "state_shadow"]},
    "state_shadow":     {"feeds": ["crash_cradle", "backup_beacon"], "consumes": ["mirror_mesh"]},
    "failover_forge":   {"feeds": ["mirror_mesh", "grace_guard"], "consumes": ["resilience_root", "duplicate_dome"]},
    "grace_guard":      {"feeds": ["crash_cradle"], "consumes": ["resilience_root", "failover_forge"]},
}


# ═══════════════════════════════════════════════════════════════════════════════
# SUBSYSTEM REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════

FORGE_GENERATORS = {
    "resilience_root":  ForgeSubsystems.resilience_root,
    "duplicate_dome":   ForgeSubsystems.duplicate_dome,
    "mirror_mesh":      ForgeSubsystems.mirror_mesh,
    "crash_cradle":     ForgeSubsystems.crash_cradle,
    "backup_beacon":    ForgeSubsystems.backup_beacon,
    "state_shadow":     ForgeSubsystems.state_shadow,
    "failover_forge":   ForgeSubsystems.failover_forge,
    "grace_guard":      ForgeSubsystems.grace_guard,
}


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/status")
async def get_full_forge_status():
    """Full Resilience Forge dashboard — all 8 subsystems."""
    subsystems = {k: gen() for k, gen in FORGE_GENERATORS.items()}

    healths = [s["health"] for s in subsystems.values()]
    statuses = [s["status"] for s in subsystems.values()]
    total_events = sum(s["events_processed"] for s in subsystems.values())

    critical_count = statuses.count("critical")
    degraded_count = statuses.count("degraded")
    offline_count = statuses.count("offline")
    active_count = statuses.count("active")

    avg_health = round(sum(healths) / len(healths), 1) if healths else 0
    min_health = min(healths) if healths else 0
    weakest = min(subsystems.values(), key=lambda s: s["health"])

    global_status = "critical" if critical_count > 2 or offline_count > 0 else \
                    "degraded" if critical_count > 0 or degraded_count > 3 else "active"

    return {
        "system": "Resilience Forge v1.0 — 8 Subsystem Citadel",
        "timestamp": datetime.utcnow().isoformat(),
        "global": {
            "status": global_status,
            "avg_health": avg_health,
            "min_health": min_health,
            "weakest_subsystem": weakest["name"],
            "subsystem_count": 8,
            "active": active_count,
            "degraded": degraded_count,
            "critical": critical_count,
            "offline": offline_count,
            "total_events_processed": total_events,
        },
        "subsystems": subsystems,
        "dependency_graph": FORGE_DEPENDENCY_GRAPH,
        "citadel_creed": "Eight pillars of resilience. The system bends but never breaks.",
    }


@router.get("/subsystem/{subsystem_id}")
async def get_forge_subsystem_detail(subsystem_id: str):
    """Get detailed state for a specific Resilience Forge subsystem."""
    gen = FORGE_GENERATORS.get(subsystem_id)
    if not gen:
        raise HTTPException(status_code=404, detail=f"Subsystem '{subsystem_id}' not found. Available: {list(FORGE_GENERATORS.keys())}")

    state = gen()
    deps = FORGE_DEPENDENCY_GRAPH.get(subsystem_id, {})

    return {
        **state,
        "dependencies": deps,
        "feeds_into": deps.get("feeds", []),
        "consumes_from": deps.get("consumes", []),
    }


@router.get("/health-matrix")
async def get_forge_health_matrix():
    """Compact health matrix for all 8 subsystems."""
    matrix = []
    for k, gen in FORGE_GENERATORS.items():
        s = gen()
        matrix.append({
            "id": s["id"],
            "name": s["name"],
            "icon": s["icon"],
            "status": s["status"],
            "health": s["health"],
            "color": s["color"],
            "events": s["events_processed"],
        })
    return {"timestamp": datetime.utcnow().isoformat(), "matrix": matrix}
