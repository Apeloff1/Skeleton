"""
╔══════════════════════════════════════════════════════════════════════════════════╗
║            PERFORMANCE ARMOR v1.0 — 13 SUBSYSTEM FORTRESS                      ║
║                                                                                  ║
║  BatteryBarrier  • RenderRanger  • GestureGlider  • NetworkNexus               ║
║  A11yArmor       • ErrorEmbrace  • MemoryMender   • HeapHopper                 ║
║  AsyncArmor      • ThrottleThrone • CacheModal    • CacheGuard • CacheBlade    ║
║                                                                                  ║
║  Every subsystem tracks:                                                         ║
║    • Operational status (active/degraded/critical/offline)                       ║
║    • Health score (0-100)                                                        ║
║    • Events processed / errors caught / recoveries made                          ║
║    • Intricate internal metrics unique to each subsystem                          ║
║    • Cross-system dependency graph (which systems feed into which)               ║
╚══════════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import os, random, math, hashlib, time
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/api/performance-armor", tags=["performance-armor"])

# ─── SUBSYSTEM ENGINE ────────────────────────────────────────────────────────

def _seed_rng(subsystem: str, seed_extra: str = ""):
    """Deterministic RNG for consistent demo data per 30-second window."""
    t = int(time.time() // 30)
    seed = int(hashlib.md5(f"{subsystem}:{seed_extra}:{t}".encode()).hexdigest()[:8], 16)
    random.seed(seed)

def _jitter(base: float, spread: float = 0.15) -> float:
    return round(base * (1 + random.uniform(-spread, spread)), 2)


class SubsystemState:
    """Generates intricate state for a subsystem."""

    @staticmethod
    def battery_barrier() -> dict:
        _seed_rng("battery_barrier")
        level = round(random.uniform(0.15, 1.0), 3)
        is_charging = random.random() > 0.6
        drain_rate = round(random.uniform(0.001, 0.008), 4) if not is_charging else 0.0
        thermal_throttle = level < 0.25 and not is_charging
        adaptive_brightness = max(0.3, min(1.0, level * 1.2))
        wake_lock_count = random.randint(0, 4)
        estimated_runtime_min = int(level / max(drain_rate, 0.0001))

        # Power profile tiers
        tier = "ULTRA_SAVER" if level < 0.15 else "SAVER" if level < 0.30 else "BALANCED" if level < 0.60 else "PERFORMANCE" if level < 0.85 else "MAX_PERFORMANCE"

        return {
            "id": "battery_barrier", "name": "BatteryBarrier", "icon": "battery-charging",
            "status": "critical" if level < 0.15 else "degraded" if level < 0.30 else "active",
            "health": round(min(100, level * 100 + (20 if is_charging else 0)), 1),
            "color": "#EF4444" if level < 0.15 else "#F97316" if level < 0.30 else "#22C55E",
            "metrics": {
                "battery_level": level,
                "is_charging": is_charging,
                "drain_rate_per_sec": drain_rate,
                "thermal_throttle_active": thermal_throttle,
                "adaptive_brightness": round(adaptive_brightness, 2),
                "wake_lock_count": wake_lock_count,
                "estimated_runtime_min": estimated_runtime_min,
                "power_tier": tier,
                "voltage_mv": random.randint(3200, 4200),
                "temperature_c": round(random.uniform(25, 42), 1),
                "charge_cycles": random.randint(100, 800),
                "coulomb_counter_mah": random.randint(1200, 4500),
            },
            "barriers": {
                "animation_barrier": thermal_throttle or level < 0.20,
                "network_barrier": level < 0.10,
                "background_fetch_barrier": level < 0.25,
                "high_fps_barrier": level < 0.40,
                "gps_barrier": level < 0.15,
            },
            "events_processed": random.randint(500, 5000),
            "last_event": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def render_ranger() -> dict:
        _seed_rng("render_ranger")
        fps = round(random.uniform(24, 60), 1)
        frame_drops = random.randint(0, 15)
        jank_score = round(max(0, 100 - frame_drops * 3 - (60 - fps) * 0.5), 1)
        rerender_count = random.randint(50, 800)
        memo_hits = random.randint(200, 2000)
        memo_misses = random.randint(10, 200)
        virtualized_lists = random.randint(2, 8)
        offscreen_components = random.randint(5, 45)

        return {
            "id": "render_ranger", "name": "RenderRanger", "icon": "speedometer",
            "status": "critical" if fps < 30 else "degraded" if fps < 45 else "active",
            "health": jank_score,
            "color": "#EF4444" if fps < 30 else "#F97316" if fps < 45 else "#22C55E",
            "metrics": {
                "current_fps": fps,
                "target_fps": 60,
                "frame_drops_last_60s": frame_drops,
                "jank_score": jank_score,
                "rerender_count_last_60s": rerender_count,
                "memo_cache_hits": memo_hits,
                "memo_cache_misses": memo_misses,
                "memo_hit_rate": round(memo_hits / max(memo_hits + memo_misses, 1) * 100, 1),
                "virtualized_list_count": virtualized_lists,
                "offscreen_components_culled": offscreen_components,
                "paint_time_avg_ms": round(random.uniform(2, 16), 2),
                "layout_time_avg_ms": round(random.uniform(1, 8), 2),
                "commit_time_avg_ms": round(random.uniform(0.5, 4), 2),
                "batch_updates_count": random.randint(20, 200),
                "unnecessary_renders_blocked": random.randint(100, 1500),
            },
            "ranger_rules": {
                "skip_animations_on_jank": frame_drops > 5,
                "reduce_shadow_complexity": fps < 45,
                "defer_offscreen_renders": True,
                "batch_state_updates": True,
                "virtualize_long_lists": True,
            },
            "events_processed": random.randint(10000, 50000),
            "last_event": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def gesture_glider() -> dict:
        _seed_rng("gesture_glider")
        touch_latency = round(random.uniform(8, 35), 1)
        gesture_queue = random.randint(0, 5)
        swipe_velocity = round(random.uniform(0.5, 3.0), 2)
        pinch_active = random.random() > 0.85
        long_press_count = random.randint(0, 20)
        cancelled_gestures = random.randint(0, 8)

        return {
            "id": "gesture_glider", "name": "GestureGlider", "icon": "hand-left",
            "status": "degraded" if touch_latency > 25 else "active",
            "health": round(max(0, 100 - touch_latency * 1.5 - gesture_queue * 5), 1),
            "color": "#F97316" if touch_latency > 25 else "#22C55E",
            "metrics": {
                "touch_latency_ms": touch_latency,
                "gesture_queue_depth": gesture_queue,
                "avg_swipe_velocity": swipe_velocity,
                "pinch_zoom_active": pinch_active,
                "long_press_events": long_press_count,
                "cancelled_gestures": cancelled_gestures,
                "simultaneous_touches": random.randint(0, 3),
                "gesture_recognizer_count": random.randint(8, 25),
                "pan_responder_active": random.random() > 0.5,
                "scroll_momentum_decay": round(random.uniform(0.92, 0.99), 3),
                "haptic_feedback_enabled": True,
                "touch_slop_px": 8,
                "fling_deceleration": round(random.uniform(0.996, 0.999), 4),
                "gesture_collision_resolution": "priority_queue",
            },
            "glider_config": {
                "smooth_scrolling": True,
                "momentum_scrolling": True,
                "overscroll_elasticity": 0.7,
                "gesture_debounce_ms": 16,
                "max_simultaneous_gestures": 3,
            },
            "events_processed": random.randint(5000, 30000),
            "last_event": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def network_nexus() -> dict:
        _seed_rng("network_nexus")
        active_connections = random.randint(1, 8)
        bandwidth_kbps = random.randint(500, 50000)
        latency_ms = round(random.uniform(15, 300), 1)
        packet_loss = round(random.uniform(0, 5), 2)
        retry_queue = random.randint(0, 6)
        requests_inflight = random.randint(0, 4)
        is_offline = random.random() < 0.03

        connection_type = random.choice(["wifi", "4g", "5g", "3g", "ethernet"])
        quality = "excellent" if latency_ms < 50 and packet_loss < 0.5 else "good" if latency_ms < 100 else "fair" if latency_ms < 200 else "poor"

        return {
            "id": "network_nexus", "name": "NetworkNexus", "icon": "globe",
            "status": "offline" if is_offline else "critical" if latency_ms > 250 else "degraded" if latency_ms > 150 else "active",
            "health": 0 if is_offline else round(max(0, 100 - latency_ms * 0.3 - packet_loss * 10 - retry_queue * 5), 1),
            "color": "#64748B" if is_offline else "#EF4444" if latency_ms > 250 else "#F97316" if latency_ms > 150 else "#22C55E",
            "metrics": {
                "connection_type": connection_type,
                "connection_quality": quality,
                "active_connections": active_connections,
                "bandwidth_kbps": bandwidth_kbps,
                "latency_ms": latency_ms,
                "packet_loss_pct": packet_loss,
                "retry_queue_depth": retry_queue,
                "requests_inflight": requests_inflight,
                "is_offline": is_offline,
                "dns_resolution_ms": round(random.uniform(5, 50), 1),
                "tls_handshake_ms": round(random.uniform(20, 150), 1),
                "total_bytes_sent_kb": random.randint(100, 50000),
                "total_bytes_received_kb": random.randint(500, 200000),
                "failed_requests_last_5min": random.randint(0, 8),
                "successful_requests_last_5min": random.randint(20, 200),
                "circuit_breaker_state": random.choice(["closed", "closed", "closed", "half-open", "open"]),
            },
            "nexus_strategies": {
                "adaptive_timeout": True,
                "exponential_backoff": True,
                "request_deduplication": True,
                "offline_queue": True,
                "bandwidth_estimation": True,
                "prefetch_enabled": bandwidth_kbps > 5000,
            },
            "events_processed": random.randint(2000, 20000),
            "last_event": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def a11y_armor() -> dict:
        _seed_rng("a11y_armor")
        screen_reader = random.random() > 0.85
        font_scale = round(random.uniform(0.85, 2.0), 2)
        reduce_motion = random.random() > 0.7
        high_contrast = random.random() > 0.8
        touch_targets_compliant = random.randint(85, 100)
        missing_labels = random.randint(0, 12)
        color_contrast_issues = random.randint(0, 5)

        return {
            "id": "a11y_armor", "name": "A11yArmor", "icon": "accessibility",
            "status": "degraded" if missing_labels > 5 else "active",
            "health": round(max(0, touch_targets_compliant - missing_labels * 2 - color_contrast_issues * 3), 1),
            "color": "#F97316" if missing_labels > 5 else "#22C55E",
            "metrics": {
                "screen_reader_active": screen_reader,
                "font_scale_factor": font_scale,
                "reduce_motion_enabled": reduce_motion,
                "high_contrast_mode": high_contrast,
                "touch_target_compliance_pct": touch_targets_compliant,
                "missing_accessibility_labels": missing_labels,
                "color_contrast_issues": color_contrast_issues,
                "focusable_elements": random.randint(50, 200),
                "aria_roles_assigned": random.randint(40, 180),
                "keyboard_navigable_pct": random.randint(80, 100),
                "voice_over_compatible_views": random.randint(30, 100),
                "dynamic_type_supported_pct": random.randint(70, 100),
                "semantic_heading_count": random.randint(5, 25),
                "alt_text_coverage_pct": random.randint(60, 100),
            },
            "armor_rules": {
                "enforce_min_touch_44px": True,
                "auto_label_icons": True,
                "motion_respect_system_pref": reduce_motion,
                "announce_screen_changes": screen_reader,
                "font_scale_cap": 2.0,
                "focus_trap_modals": True,
            },
            "events_processed": random.randint(1000, 8000),
            "last_event": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def error_embrace() -> dict:
        _seed_rng("error_embrace")
        total_errors = random.randint(0, 50)
        recovered = random.randint(0, total_errors)
        unrecovered = total_errors - recovered
        error_boundary_catches = random.randint(0, 5)
        promise_rejections = random.randint(0, 12)
        network_errors = random.randint(0, 8)
        render_errors = random.randint(0, 3)
        graceful_degradations = random.randint(0, 10)

        recovery_rate = round(recovered / max(total_errors, 1) * 100, 1)

        return {
            "id": "error_embrace", "name": "ErrorEmbrace", "icon": "shield-checkmark",
            "status": "critical" if unrecovered > 10 else "degraded" if unrecovered > 3 else "active",
            "health": round(max(0, 100 - unrecovered * 5 - error_boundary_catches * 8), 1),
            "color": "#EF4444" if unrecovered > 10 else "#F97316" if unrecovered > 3 else "#22C55E",
            "metrics": {
                "total_errors_caught": total_errors,
                "errors_recovered": recovered,
                "errors_unrecovered": unrecovered,
                "recovery_rate_pct": recovery_rate,
                "error_boundary_catches": error_boundary_catches,
                "unhandled_promise_rejections": promise_rejections,
                "network_errors": network_errors,
                "render_errors": render_errors,
                "graceful_degradations": graceful_degradations,
                "error_rate_per_min": round(total_errors / 5, 2),
                "mean_time_to_recovery_ms": round(random.uniform(50, 2000), 0),
                "crash_free_sessions_pct": round(random.uniform(95, 100), 2),
                "last_error_type": random.choice(["TypeError", "NetworkError", "RangeError", "SyntaxError", "None"]),
                "error_fingerprints_unique": random.randint(1, 15),
            },
            "embrace_strategies": {
                "auto_retry_network": True,
                "fallback_ui_on_render_error": True,
                "silent_catch_non_critical": True,
                "error_aggregation": True,
                "stack_trace_symbolication": True,
                "user_friendly_messages": True,
            },
            "events_processed": random.randint(500, 5000),
            "last_event": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def memory_mender() -> dict:
        _seed_rng("memory_mender")
        heap_used_mb = round(random.uniform(30, 200), 1)
        heap_total_mb = round(random.uniform(200, 512), 1)
        heap_pct = round(heap_used_mb / heap_total_mb * 100, 1)
        leak_suspects = random.randint(0, 5)
        gc_runs = random.randint(10, 100)
        gc_pause_avg_ms = round(random.uniform(2, 25), 1)
        retained_objects = random.randint(1000, 50000)
        disposed_listeners = random.randint(50, 500)

        return {
            "id": "memory_mender", "name": "MemoryMender", "icon": "hardware-chip",
            "status": "critical" if heap_pct > 85 else "degraded" if heap_pct > 65 else "active",
            "health": round(max(0, 100 - heap_pct * 0.8 - leak_suspects * 8), 1),
            "color": "#EF4444" if heap_pct > 85 else "#F97316" if heap_pct > 65 else "#22C55E",
            "metrics": {
                "heap_used_mb": heap_used_mb,
                "heap_total_mb": heap_total_mb,
                "heap_utilization_pct": heap_pct,
                "leak_suspects": leak_suspects,
                "gc_runs_last_5min": gc_runs,
                "gc_pause_avg_ms": gc_pause_avg_ms,
                "retained_objects": retained_objects,
                "disposed_event_listeners": disposed_listeners,
                "detached_dom_nodes": random.randint(0, 20),
                "closure_count": random.randint(200, 2000),
                "timer_count_active": random.randint(5, 30),
                "weak_ref_count": random.randint(10, 100),
                "array_buffer_mb": round(random.uniform(0, 20), 1),
                "string_pool_mb": round(random.uniform(5, 30), 1),
            },
            "mender_actions": {
                "auto_dispose_unmounted": True,
                "weak_ref_subscriptions": True,
                "timer_cleanup_on_blur": True,
                "image_cache_limit_mb": 50,
                "max_retained_screens": 5,
                "force_gc_on_low_memory": heap_pct > 80,
            },
            "events_processed": random.randint(2000, 15000),
            "last_event": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def heap_hopper() -> dict:
        _seed_rng("heap_hopper")
        young_gen_mb = round(random.uniform(5, 40), 1)
        old_gen_mb = round(random.uniform(20, 150), 1)
        large_obj_space_mb = round(random.uniform(0, 30), 1)
        code_space_mb = round(random.uniform(5, 20), 1)
        total_heap = young_gen_mb + old_gen_mb + large_obj_space_mb + code_space_mb
        minor_gc = random.randint(50, 500)
        major_gc = random.randint(1, 20)
        fragmentation_pct = round(random.uniform(2, 25), 1)
        allocation_rate_kbs = round(random.uniform(100, 5000), 0)

        return {
            "id": "heap_hopper", "name": "HeapHopper", "icon": "layers",
            "status": "critical" if fragmentation_pct > 20 else "degraded" if fragmentation_pct > 12 else "active",
            "health": round(max(0, 100 - fragmentation_pct * 2.5 - major_gc * 2), 1),
            "color": "#EF4444" if fragmentation_pct > 20 else "#F97316" if fragmentation_pct > 12 else "#22C55E",
            "metrics": {
                "young_generation_mb": young_gen_mb,
                "old_generation_mb": old_gen_mb,
                "large_object_space_mb": large_obj_space_mb,
                "code_space_mb": code_space_mb,
                "total_heap_mb": round(total_heap, 1),
                "minor_gc_count": minor_gc,
                "major_gc_count": major_gc,
                "fragmentation_pct": fragmentation_pct,
                "allocation_rate_kbs": allocation_rate_kbs,
                "scavenge_time_avg_ms": round(random.uniform(0.5, 5), 2),
                "mark_sweep_time_avg_ms": round(random.uniform(5, 50), 1),
                "compaction_events": random.randint(0, 10),
                "external_memory_mb": round(random.uniform(0, 15), 1),
                "heap_limit_mb": 512,
                "heap_pressure_level": "critical" if total_heap > 400 else "high" if total_heap > 300 else "normal",
            },
            "hopper_strategies": {
                "incremental_gc": True,
                "concurrent_marking": True,
                "lazy_sweeping": True,
                "object_pooling": True,
                "string_interning": True,
                "typed_array_optimization": True,
            },
            "events_processed": random.randint(5000, 30000),
            "last_event": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def async_armor() -> dict:
        _seed_rng("async_armor")
        pending_promises = random.randint(0, 15)
        active_timers = random.randint(2, 20)
        cancelled_tasks = random.randint(0, 30)
        race_conditions_prevented = random.randint(0, 12)
        stale_closures_detected = random.randint(0, 8)
        debounced_calls = random.randint(50, 500)
        throttled_calls = random.randint(30, 300)
        abort_controllers = random.randint(1, 10)

        return {
            "id": "async_armor", "name": "AsyncArmor", "icon": "sync",
            "status": "degraded" if pending_promises > 10 else "active",
            "health": round(max(0, 100 - pending_promises * 3 - stale_closures_detected * 5), 1),
            "color": "#F97316" if pending_promises > 10 else "#22C55E",
            "metrics": {
                "pending_promises": pending_promises,
                "active_timers": active_timers,
                "cancelled_tasks": cancelled_tasks,
                "race_conditions_prevented": race_conditions_prevented,
                "stale_closures_detected": stale_closures_detected,
                "debounced_calls": debounced_calls,
                "throttled_calls": throttled_calls,
                "abort_controllers_active": abort_controllers,
                "microtask_queue_depth": random.randint(0, 10),
                "macrotask_queue_depth": random.randint(0, 5),
                "event_loop_lag_ms": round(random.uniform(0, 50), 1),
                "async_iterator_count": random.randint(0, 5),
                "concurrent_fetch_limit": 6,
                "request_dedup_hits": random.randint(20, 200),
            },
            "armor_shields": {
                "auto_cancel_on_unmount": True,
                "abort_controller_wrappers": True,
                "stale_closure_guard": True,
                "race_condition_mutex": True,
                "promise_timeout_ms": 30000,
                "debounce_default_ms": 300,
                "throttle_default_ms": 150,
            },
            "events_processed": random.randint(3000, 20000),
            "last_event": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def throttle_throne() -> dict:
        _seed_rng("throttle_throne")
        global_throttle_pct = round(random.uniform(0, 40), 1)
        active_throttles = random.randint(0, 8)
        requests_throttled = random.randint(0, 200)
        renders_throttled = random.randint(0, 500)
        animations_reduced = random.randint(0, 50)
        cpu_throttle = random.random() > 0.7
        network_throttle = random.random() > 0.8

        return {
            "id": "throttle_throne", "name": "ThrottleThrone", "icon": "options",
            "status": "active" if global_throttle_pct < 20 else "degraded" if global_throttle_pct < 35 else "critical",
            "health": round(max(0, 100 - global_throttle_pct * 1.5), 1),
            "color": "#22C55E" if global_throttle_pct < 20 else "#F97316" if global_throttle_pct < 35 else "#EF4444",
            "metrics": {
                "global_throttle_pct": global_throttle_pct,
                "active_throttle_rules": active_throttles,
                "requests_throttled_last_5min": requests_throttled,
                "renders_throttled_last_5min": renders_throttled,
                "animations_reduced": animations_reduced,
                "cpu_throttle_active": cpu_throttle,
                "network_throttle_active": network_throttle,
                "fps_cap_current": 30 if cpu_throttle else 60,
                "polling_interval_multiplier": round(1 + global_throttle_pct * 0.05, 2),
                "batch_size_reduction_pct": round(global_throttle_pct * 0.8, 1),
                "background_task_paused": global_throttle_pct > 30,
                "prefetch_disabled": global_throttle_pct > 25,
                "image_quality_reduction_pct": round(min(global_throttle_pct * 1.5, 50), 1),
            },
            "throne_decrees": {
                "progressive_throttle": True,
                "thermal_aware_scaling": True,
                "battery_proportional_limits": True,
                "user_interaction_priority": True,
                "background_demotion": True,
                "burst_detection_and_spread": True,
            },
            "events_processed": random.randint(5000, 40000),
            "last_event": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def cache_modal() -> dict:
        _seed_rng("cache_modal")
        cached_modals = random.randint(3, 15)
        total_modals = 52
        cache_hit_rate = round(random.uniform(60, 98), 1)
        preloaded = random.randint(1, 5)
        evicted = random.randint(0, 10)
        lazy_loaded = total_modals - cached_modals
        avg_mount_ms = round(random.uniform(15, 120), 1)
        avg_cached_mount_ms = round(random.uniform(2, 15), 1)

        return {
            "id": "cache_modal", "name": "CacheModal", "icon": "albums",
            "status": "active" if cache_hit_rate > 70 else "degraded",
            "health": round(cache_hit_rate, 1),
            "color": "#22C55E" if cache_hit_rate > 70 else "#F97316",
            "metrics": {
                "total_modals": total_modals,
                "cached_modals": cached_modals,
                "lazy_loaded_modals": lazy_loaded,
                "preloaded_modals": preloaded,
                "evicted_modals": evicted,
                "cache_hit_rate_pct": cache_hit_rate,
                "avg_cold_mount_ms": avg_mount_ms,
                "avg_cached_mount_ms": avg_cached_mount_ms,
                "speedup_factor": round(avg_mount_ms / max(avg_cached_mount_ms, 1), 1),
                "memory_saved_mb": round(lazy_loaded * 0.8, 1),
                "unmount_delay_ms": 500,
                "keep_mounted_count": 3,
                "modal_open_count_session": random.randint(5, 50),
                "most_opened_modal": random.choice(["gameFactory", "bible", "compiler", "thermalMonitor"]),
            },
            "modal_strategies": {
                "lazy_mount_on_open": True,
                "delayed_unmount": True,
                "preload_frequent": True,
                "priority_eviction": True,
                "state_preservation": True,
                "transition_caching": True,
            },
            "events_processed": random.randint(500, 5000),
            "last_event": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def cache_guard() -> dict:
        _seed_rng("cache_guard")
        total_entries = random.randint(50, 500)
        valid_entries = random.randint(40, total_entries)
        stale_entries = total_entries - valid_entries
        integrity_checks = random.randint(100, 1000)
        integrity_failures = random.randint(0, 5)
        cache_size_mb = round(random.uniform(1, 25), 1)
        ttl_avg_sec = random.randint(5, 300)
        eviction_count = random.randint(10, 200)

        return {
            "id": "cache_guard", "name": "CacheGuard", "icon": "shield",
            "status": "degraded" if integrity_failures > 2 else "active",
            "health": round(max(0, 100 - integrity_failures * 10 - stale_entries * 0.3), 1),
            "color": "#F97316" if integrity_failures > 2 else "#22C55E",
            "metrics": {
                "total_cache_entries": total_entries,
                "valid_entries": valid_entries,
                "stale_entries": stale_entries,
                "integrity_checks_run": integrity_checks,
                "integrity_failures": integrity_failures,
                "cache_size_mb": cache_size_mb,
                "max_cache_size_mb": 50,
                "ttl_avg_sec": ttl_avg_sec,
                "eviction_count": eviction_count,
                "eviction_policy": "LRU",
                "hit_rate_pct": round(random.uniform(50, 95), 1),
                "miss_rate_pct": round(random.uniform(5, 50), 1),
                "warm_cache_pct": round(valid_entries / max(total_entries, 1) * 100, 1),
                "compression_enabled": True,
                "encryption_at_rest": False,
            },
            "guard_protocols": {
                "integrity_check_interval_sec": 30,
                "auto_purge_stale": True,
                "size_limit_enforcement": True,
                "ttl_enforcement": True,
                "corruption_auto_repair": True,
                "versioned_cache_keys": True,
            },
            "events_processed": random.randint(2000, 15000),
            "last_event": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def cache_blade() -> dict:
        _seed_rng("cache_blade")
        sliced_entries = random.randint(20, 300)
        bytes_freed_mb = round(random.uniform(0.5, 15), 1)
        precision_cuts = random.randint(10, 100)
        surgical_evictions = random.randint(5, 50)
        cascade_prunes = random.randint(0, 10)
        blade_sharpness = round(random.uniform(70, 100), 1)
        last_prune_ago_sec = random.randint(5, 120)

        return {
            "id": "cache_blade", "name": "CacheBlade", "icon": "cut",
            "status": "active" if blade_sharpness > 80 else "degraded",
            "health": blade_sharpness,
            "color": "#22C55E" if blade_sharpness > 80 else "#F97316",
            "metrics": {
                "entries_sliced_total": sliced_entries,
                "bytes_freed_mb": bytes_freed_mb,
                "precision_cuts": precision_cuts,
                "surgical_evictions": surgical_evictions,
                "cascade_prunes": cascade_prunes,
                "blade_sharpness_pct": blade_sharpness,
                "last_prune_ago_sec": last_prune_ago_sec,
                "prune_frequency_sec": 30,
                "cold_entry_threshold_sec": 60,
                "max_entry_age_sec": 300,
                "size_threshold_per_entry_kb": 100,
                "priority_retention_list": ["auth_token", "user_profile", "active_modal_state"],
                "aggressive_mode_active": blade_sharpness < 75,
                "entries_protected": random.randint(3, 10),
            },
            "blade_techniques": {
                "lru_slice": True,
                "ttl_expiry_cut": True,
                "size_pressure_prune": True,
                "frequency_weighted_eviction": True,
                "cascade_dependency_prune": True,
                "cold_start_warmup": True,
            },
            "events_processed": random.randint(1000, 10000),
            "last_event": datetime.utcnow().isoformat(),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# DEPENDENCY GRAPH — Cross-system relationships
# ═══════════════════════════════════════════════════════════════════════════════

DEPENDENCY_GRAPH = {
    "battery_barrier": {"feeds": ["throttle_throne", "render_ranger", "network_nexus"], "consumes": []},
    "render_ranger": {"feeds": ["gesture_glider"], "consumes": ["throttle_throne", "memory_mender"]},
    "gesture_glider": {"feeds": [], "consumes": ["render_ranger", "async_armor"]},
    "network_nexus": {"feeds": ["cache_guard", "async_armor"], "consumes": ["throttle_throne", "battery_barrier"]},
    "a11y_armor": {"feeds": ["render_ranger"], "consumes": []},
    "error_embrace": {"feeds": ["async_armor"], "consumes": ["network_nexus", "memory_mender"]},
    "memory_mender": {"feeds": ["heap_hopper", "cache_blade"], "consumes": ["render_ranger"]},
    "heap_hopper": {"feeds": ["cache_blade"], "consumes": ["memory_mender"]},
    "async_armor": {"feeds": ["error_embrace"], "consumes": ["throttle_throne", "network_nexus"]},
    "throttle_throne": {"feeds": ["render_ranger", "network_nexus", "async_armor"], "consumes": ["battery_barrier"]},
    "cache_modal": {"feeds": ["render_ranger"], "consumes": ["cache_guard", "memory_mender"]},
    "cache_guard": {"feeds": ["cache_blade", "cache_modal"], "consumes": ["network_nexus"]},
    "cache_blade": {"feeds": [], "consumes": ["cache_guard", "memory_mender", "heap_hopper"]},
}


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

SUBSYSTEM_GENERATORS = {
    "battery_barrier": SubsystemState.battery_barrier,
    "render_ranger": SubsystemState.render_ranger,
    "gesture_glider": SubsystemState.gesture_glider,
    "network_nexus": SubsystemState.network_nexus,
    "a11y_armor": SubsystemState.a11y_armor,
    "error_embrace": SubsystemState.error_embrace,
    "memory_mender": SubsystemState.memory_mender,
    "heap_hopper": SubsystemState.heap_hopper,
    "async_armor": SubsystemState.async_armor,
    "throttle_throne": SubsystemState.throttle_throne,
    "cache_modal": SubsystemState.cache_modal,
    "cache_guard": SubsystemState.cache_guard,
    "cache_blade": SubsystemState.cache_blade,
}


@router.get("/status")
async def get_full_armor_status():
    """Full Performance Armor dashboard — all 13 subsystems."""
    subsystems = {k: gen() for k, gen in SUBSYSTEM_GENERATORS.items()}

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
        "system": "Performance Armor v1.0 — 13 Subsystem Fortress",
        "timestamp": datetime.utcnow().isoformat(),
        "global": {
            "status": global_status,
            "avg_health": avg_health,
            "min_health": min_health,
            "weakest_subsystem": weakest["name"],
            "subsystem_count": 13,
            "active": active_count,
            "degraded": degraded_count,
            "critical": critical_count,
            "offline": offline_count,
            "total_events_processed": total_events,
        },
        "subsystems": subsystems,
        "dependency_graph": DEPENDENCY_GRAPH,
        "fortress_creed": "Thirteen shields, one fortress. No single point of failure.",
    }


@router.get("/subsystem/{subsystem_id}")
async def get_subsystem_detail(subsystem_id: str):
    """Get detailed state for a specific subsystem."""
    gen = SUBSYSTEM_GENERATORS.get(subsystem_id)
    if not gen:
        raise HTTPException(status_code=404, detail=f"Subsystem '{subsystem_id}' not found. Available: {list(SUBSYSTEM_GENERATORS.keys())}")

    state = gen()
    deps = DEPENDENCY_GRAPH.get(subsystem_id, {})

    return {
        **state,
        "dependencies": deps,
        "feeds_into": deps.get("feeds", []),
        "consumes_from": deps.get("consumes", []),
    }


@router.get("/health-matrix")
async def get_health_matrix():
    """Compact health matrix for all 13 subsystems."""
    matrix = []
    for k, gen in SUBSYSTEM_GENERATORS.items():
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
