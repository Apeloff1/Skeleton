"""Immutable aggregate policy for the worker execution plane."""

from __future__ import annotations

from dataclasses import dataclass,replace

from skeleton.shells.worker_backpressure import BackpressurePolicy
from skeleton.shells.worker_heartbeat import HeartbeatPolicy
from skeleton.shells.worker_quota import WorkerQuota
from skeleton.shells.worker_recovery import RecoveryPolicy
from skeleton.shells.worker_supervisor import SupervisorPolicy


@dataclass(frozen=True)
class WorkerPlanePolicy:
    max_workers:int=4096
    max_queue_items:int=4096
    max_assignments:int=10000
    max_reservations:int=10000
    max_journal_events:int=100000
    max_metrics_workers:int=4096
    max_events:int=10000
    heartbeat:HeartbeatPolicy=HeartbeatPolicy()
    backpressure:BackpressurePolicy=BackpressurePolicy()
    quota:WorkerQuota=WorkerQuota()
    recovery:RecoveryPolicy=RecoveryPolicy()
    supervisor:SupervisorPolicy=SupervisorPolicy()

    def __post_init__(self)->None:
        values=(
            self.max_workers,self.max_queue_items,self.max_assignments,
            self.max_reservations,self.max_journal_events,
            self.max_metrics_workers,self.max_events,
        )
        if any(isinstance(value,bool) or not isinstance(value,int) or value<=0 for value in values):
            raise ValueError("worker plane capacities must be positive integers")

    def to_dict(self)->dict[str,object]:
        return {
            "max_workers":self.max_workers,
            "max_queue_items":self.max_queue_items,
            "max_assignments":self.max_assignments,
            "max_reservations":self.max_reservations,
            "max_journal_events":self.max_journal_events,
            "max_metrics_workers":self.max_metrics_workers,
            "max_events":self.max_events,
            "heartbeat":{
                "late_after_seconds":self.heartbeat.late_after_seconds,
                "stale_after_seconds":self.heartbeat.stale_after_seconds,
                "max_sequence_gap":self.heartbeat.max_sequence_gap,
                "max_metrics":self.heartbeat.max_metrics,
            },
            "backpressure":{
                "queue_high_watermark":self.backpressure.queue_high_watermark,
                "queue_critical_watermark":self.backpressure.queue_critical_watermark,
                "inflight_high_watermark":self.backpressure.inflight_high_watermark,
                "inflight_critical_watermark":self.backpressure.inflight_critical_watermark,
                "failure_ratio_high":self.backpressure.failure_ratio_high,
                "failure_ratio_critical":self.backpressure.failure_ratio_critical,
                "latency_high_ms":self.backpressure.latency_high_ms,
                "latency_critical_ms":self.backpressure.latency_critical_ms,
                "recovery_samples":self.backpressure.recovery_samples,
                "throttle_factor":self.backpressure.throttle_factor,
                "ewma_alpha":self.backpressure.ewma_alpha,
            },
            "quota":{
                "max_inflight":self.quota.max_inflight,
                "max_starts_per_window":self.quota.max_starts_per_window,
                "window_seconds":self.quota.window_seconds,
                "max_failures_per_window":self.quota.max_failures_per_window,
                "max_output_bytes_per_window":self.quota.max_output_bytes_per_window,
            },
            "recovery":{
                "stale_claim_after_seconds":self.recovery.stale_claim_after_seconds,
                "priority_delta_on_recovery":self.recovery.priority_delta_on_recovery,
                "disable_stale_workers":self.recovery.disable_stale_workers,
                "unregister_stale_workers":self.recovery.unregister_stale_workers,
                "max_recoveries_per_pass":self.recovery.max_recoveries_per_pass,
            },
            "supervisor":{
                "max_faults":self.supervisor.max_faults,
                "fault_window_seconds":self.supervisor.fault_window_seconds,
                "quarantine_seconds":self.supervisor.quarantine_seconds,
                "max_restarts":self.supervisor.max_restarts,
                "restart_window_seconds":self.supervisor.restart_window_seconds,
            },
        }

    def no_wider_than(self,parent:"WorkerPlanePolicy")->bool:
        scalar=(
            self.max_workers<=parent.max_workers
            and self.max_queue_items<=parent.max_queue_items
            and self.max_assignments<=parent.max_assignments
            and self.max_reservations<=parent.max_reservations
            and self.max_journal_events<=parent.max_journal_events
            and self.max_metrics_workers<=parent.max_metrics_workers
            and self.max_events<=parent.max_events
        )
        heartbeat=(
            self.heartbeat.late_after_seconds<=parent.heartbeat.late_after_seconds
            and self.heartbeat.stale_after_seconds<=parent.heartbeat.stale_after_seconds
            and self.heartbeat.max_sequence_gap<=parent.heartbeat.max_sequence_gap
            and self.heartbeat.max_metrics<=parent.heartbeat.max_metrics
        )
        quota=(
            self.quota.max_inflight<=parent.quota.max_inflight
            and self.quota.max_starts_per_window<=parent.quota.max_starts_per_window
            and self.quota.max_failures_per_window<=parent.quota.max_failures_per_window
            and self.quota.max_output_bytes_per_window<=parent.quota.max_output_bytes_per_window
            and self.quota.window_seconds>=parent.quota.window_seconds
        )
        recovery=(
            self.recovery.max_recoveries_per_pass<=parent.recovery.max_recoveries_per_pass
            and self.recovery.stale_claim_after_seconds<=parent.recovery.stale_claim_after_seconds
        )
        supervisor=(
            self.supervisor.max_faults<=parent.supervisor.max_faults
            and self.supervisor.max_restarts<=parent.supervisor.max_restarts
        )
        return scalar and heartbeat and quota and recovery and supervisor

    def narrow(self,**changes)->"WorkerPlanePolicy":
        child=replace(self,**changes)
        if not child.no_wider_than(self):
            raise ValueError("worker plane policy narrowing would widen authority or capacity")
        return child
