"""Skeleton CLI entry point.

Provides a comprehensive command-line interface for all subsystems:
- Policy management and rollback
- Repair orchestration and diagnostics
- Lattice inspection and steering
- KV cache, mouth, LoRA, decoder operations
- Swarm coordination and telemetry streaming
- Benchmark suite and deployment packaging
- Resilience patterns (circuit breaker, retry, bulkhead)
- Observability (tracing, audit, events, metrics, anomalies)
- Dashboard and push server control
- Feature flags, config, schema registry, secret management
- Developer tools (scaffold, wizard, health, visualize, extension)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skeleton.cortex.deck import CommandDeck
from skeleton.cortex.operator_dashboard import OperatorDashboard
from skeleton.cortex.push_server import DashboardPushServer
from skeleton.observability.audit_logging import AuditLog
from skeleton.observability.distributed_tracing import Tracer
from skeleton.observability.event_sourcing import EventStore
from skeleton.observability.anomaly_detector import AnomalyDetector
from skeleton.observability.metrics_exporter import MetricsExporter
from skeleton.organism.config_manager import ConfigManager
from skeleton.organism.feature_flags import FeatureFlagRegistry
from skeleton.organism.schema_registry import SchemaRegistry
from skeleton.organism.secret_manager import SecretManager
from skeleton.resilience.auto_scaler import AutoScaler
from skeleton.resilience.health_probes import HealthProbeAggregator
from skeleton.resilience.load_shedder import LoadShedder
from skeleton.resilience.rate_limiter import RateLimiter


def main() -> None:
    parser = argparse.ArgumentParser(description="Skeleton CLI")
    sub = parser.add_subparsers(dest="command")

    # Policy
    p_policy = sub.add_parser("policy", help="Policy management")
    p_policy.add_argument("--rollback", type=str, help="Rollback to version")
    p_policy.add_argument("--state", action="store_true", help="Show policy state")

    # Repair
    p_repair = sub.add_parser("repair", help="Repair orchestration")
    p_repair.add_argument("--surface", type=str, default="forge")
    p_repair.add_argument("--trigger", type=str, default="_probe")
    p_repair.add_argument("--diagnose", action="store_true", help="Run diagnostics")

    # Lattice
    p_lattice = sub.add_parser("lattice", help="Lattice inspection")
    p_lattice.add_argument("--hud", action="store_true", help="Show HUD")

    # Steering
    p_steering = sub.add_parser("steering", help="Steering control")
    p_steering.add_argument("--composite", action="store_true", help="Show composite")

    # KV Cache
    p_kv = sub.add_parser("kv", help="KV cache operations")
    p_kv.add_argument("--stats", action="store_true", help="Show stats")

    # Mouth
    p_mouth = sub.add_parser("mouth", help="Mouth binding")
    p_mouth.add_argument("--current", action="store_true", help="Show current")

    # LoRA
    p_lora = sub.add_parser("lora", help="LoRA management")
    p_lora.add_argument("--card", action="store_true", help="Show card")

    # Decoder
    p_decoder = sub.add_parser("decoder", help="Decoder operations")
    p_decoder.add_argument("--card", action="store_true", help="Show card")

    # Swarm
    p_swarm = sub.add_parser("swarm", help="Swarm coordination")
    p_swarm.add_argument("--card", action="store_true", help="Show swarm card")
    p_swarm.add_argument("--spawn", type=int, help="Spawn N agents")

    # Telemetry
    p_telemetry = sub.add_parser("telemetry", help="Telemetry streaming")
    p_telemetry.add_argument("--stats", action="store_true", help="Show stats")
    p_telemetry.add_argument("--stream", action="store_true", help="Start stream")

    # Benchmark
    p_benchmark = sub.add_parser("benchmark", help="Benchmark suite")
    p_benchmark.add_argument("--run", action="store_true", help="Run benchmarks")
    p_benchmark.add_argument("--card", action="store_true", help="Show card")

    # Deployment
    p_deploy = sub.add_parser("deploy", help="Deployment packaging")
    p_deploy.add_argument("--manifests", action="store_true", help="Show manifests")
    p_deploy.add_argument("--package", type=str, help="Package target")

    # Resilience
    p_resilience = sub.add_parser("resilience", help="Resilience patterns")
    p_resilience.add_argument("--circuit", action="store_true", help="Circuit breaker card")
    p_resilience.add_argument("--retry", action="store_true", help="Retry card")
    p_resilience.add_argument("--bulkhead", action="store_true", help="Bulkhead card")
    p_resilience.add_argument("--load-shedder", action="store_true", help="Load shedder card")
    p_resilience.add_argument("--health", action="store_true", help="Health probes card")
    p_resilience.add_argument("--rate-limiter", action="store_true", help="Rate limiter card")

    # Observability
    p_obs = sub.add_parser("observability", help="Observability tools")
    p_obs.add_argument("--tracer", action="store_true", help="Tracer card")
    p_obs.add_argument("--audit", action="store_true", help="Audit log card")
    p_obs.add_argument("--events", action="store_true", help="Event store card")
    p_obs.add_argument("--anomaly", action="store_true", help="Anomaly detector card")
    p_obs.add_argument("--metrics", action="store_true", help="Metrics exporter card")
    p_obs.add_argument("--trace", type=str, help="Start trace span")
    p_obs.add_argument("--record", nargs=3, metavar=("ACTOR", "ACTION", "RESOURCE"), help="Record audit entry")
    p_obs.add_argument("--append-event", nargs=2, metavar=("AGGREGATE", "EVENT_TYPE"), help="Append domain event")

    # Dashboard
    p_dash = sub.add_parser("dashboard", help="Operator dashboard")
    p_dash.add_argument("--card", action="store_true", help="Show dashboard card")
    p_dash.add_argument("--fire-alert", nargs=2, metavar=("SEVERITY", "MESSAGE"), help="Fire alert")
    p_dash.add_argument("--ack", type=str, help="Acknowledge alert")
    p_dash.add_argument("--resolve", type=str, help="Resolve alert")
    p_dash.add_argument("--push-start", action="store_true", help="Start push server")
    p_dash.add_argument("--push-stop", action="store_true", help="Stop push server")

    # Feature Flags
    p_flags = sub.add_parser("flags", help="Feature flags")
    p_flags.add_argument("--list", action="store_true", help="List flags")
    p_flags.add_argument("--register", nargs=2, metavar=("NAME", "ENABLED"), help="Register flag")
    p_flags.add_argument("--set", nargs=2, metavar=("NAME", "ENABLED"), help="Set flag")
    p_flags.add_argument("--check", type=str, help="Check flag")

    # Config
    p_config = sub.add_parser("config", help="Configuration")
    p_config.add_argument("--get", type=str, help="Get config value")
    p_config.add_argument("--set", nargs=2, metavar=("PATH", "VALUE"), help="Set config value")
    p_config.add_argument("--card", action="store_true", help="Show config card")
    p_config.add_argument("--reload", action="store_true", help="Reload config")

    # Schema Registry
    p_schema = sub.add_parser("schema", help="Schema registry")
    p_schema.add_argument("--register", nargs=2, metavar=("NAME", "VERSION"), help="Register schema")
    p_schema.add_argument("--validate", nargs=2, metavar=("NAME", "DATA"), help="Validate data")
    p_schema.add_argument("--card", action="store_true", help="Show schema card")

    # Secrets
    p_secrets = sub.add_parser("secrets", help="Secret management")
    p_secrets.add_argument("--set", nargs=2, metavar=("NAME", "VALUE"), help="Set secret")
    p_secrets.add_argument("--get", type=str, help="Get secret")
    p_secrets.add_argument("--rotate", nargs=2, metavar=("NAME", "VALUE"), help="Rotate secret")
    p_secrets.add_argument("--card", action="store_true", help="Show secrets card")

    # Meta
    p_meta = sub.add_parser("meta", help="Meta information")
    p_meta.add_argument("--card", action="store_true", help="Show command deck meta")

    # Developer tools
    p_dev = sub.add_parser("dev", help="Developer tools (scaffold, wizard, health, visualize, extension)")
    p_dev.add_argument("subcommand", nargs="?", help="Dev subcommand (scaffold, wizard, health, visualize, extension, list-templates, validate, docs)")
    p_dev.add_argument("args", nargs=argparse.REMAINDER, help="Arguments for the subcommand")

    args = parser.parse_args()
    deck = CommandDeck()

    if args.command == "policy":
        if args.rollback:
            print(json.dumps(deck.policy_rollback(args.rollback), indent=2))
        elif args.state:
            print(json.dumps(deck.policy_state(), indent=2))

    elif args.command == "repair":
        if args.diagnose:
            print(json.dumps({
                "errors": deck.repair_errors(),
                "learned": deck.repair_learned(),
                "effectiveness": deck.repair_effectiveness(),
                "telemetry": deck.repair_telemetry(),
            }, indent=2))
        else:
            print(json.dumps(deck.repair_orchestrate(args.surface, args.trigger), indent=2))

    elif args.command == "lattice":
        if args.hud:
            print(json.dumps(deck.lattice_hud(), indent=2))

    elif args.command == "steering":
        if args.composite:
            print(json.dumps(deck.steering_composite(), indent=2))

    elif args.command == "kv":
        if args.stats:
            print(json.dumps(deck.kv_cache_stats(), indent=2))

    elif args.command == "mouth":
        if args.current:
            print(json.dumps(deck.mouth_current(), indent=2))

    elif args.command == "lora":
        if args.card:
            print(json.dumps(deck.lora_card(), indent=2))

    elif args.command == "decoder":
        if args.card:
            print(json.dumps(deck.decoder_card(), indent=2))

    elif args.command == "swarm":
        if args.card:
            print(json.dumps(deck.swarm_card(), indent=2))
        elif args.spawn:
            print(json.dumps({"spawned": args.spawn}, indent=2))

    elif args.command == "telemetry":
        if args.stats:
            print(json.dumps(deck.telemetry_stats(), indent=2))
        elif args.stream:
            print(json.dumps({"status": "streaming"}, indent=2))

    elif args.command == "benchmark":
        if args.run:
            print(json.dumps({"status": "running"}, indent=2))
        elif args.card:
            print(json.dumps(deck.benchmark_card(), indent=2))

    elif args.command == "deploy":
        if args.manifests:
            print(json.dumps(deck.deployment_manifests(), indent=2))
        elif args.package:
            print(json.dumps({"packaged": args.package}, indent=2))

    elif args.command == "resilience":
        if args.circuit:
            print(json.dumps(deck.circuit_card(), indent=2))
        elif args.retry:
            print(json.dumps(deck.retry_card(), indent=2))
        elif args.bulkhead:
            print(json.dumps(deck.bulkhead_card(), indent=2))
        elif args.load_shedder:
            print(json.dumps(deck.load_shedder_card(), indent=2))
        elif args.health:
            print(json.dumps(deck.health_probe_card(), indent=2))
        elif args.rate_limiter:
            print(json.dumps(deck.rate_limiter_card(), indent=2))

    elif args.command == "observability":
        if args.tracer:
            print(json.dumps(deck.tracer_card(), indent=2))
        elif args.audit:
            print(json.dumps(deck.audit_card(), indent=2))
        elif args.events:
            print(json.dumps(deck.event_store_card(), indent=2))
        elif args.anomaly:
            print(json.dumps(deck.anomaly_detector.card(), indent=2))
        elif args.metrics:
            print(json.dumps(deck.metrics.card(), indent=2))
        elif args.trace:
            span = deck.tracer.start_span(args.trace)
            deck.tracer.finish_span(span)
            print(json.dumps({"traced": args.trace, "span": span.to_dict()}, indent=2))
        elif args.record:
            entry = deck.audit.record(args.record[0], args.record[1], args.record[2])
            print(json.dumps({"recorded": entry.to_dict()}, indent=2))
        elif args.append_event:
            event = deck.event_store.append(args.append_event[0], args.append_event[1], {})
            print(json.dumps({"appended": event.to_dict()}, indent=2))

    elif args.command == "dashboard":
        if args.card:
            print(json.dumps(deck.dashboard_card(), indent=2))
        elif args.fire_alert:
            alert = deck.dashboard.fire_alert(args.fire_alert[0], "cli", args.fire_alert[1])
            print(json.dumps({"fired": alert.to_dict()}, indent=2))
        elif args.ack:
            print(json.dumps({"acknowledged": deck.dashboard.acknowledge_alert(args.ack)}, indent=2))
        elif args.resolve:
            print(json.dumps({"resolved": deck.dashboard.resolve_alert(args.resolve)}, indent=2))
        elif args.push_start:
            deck.push_server.start()
            print(json.dumps({"push_server": "started"}, indent=2))
        elif args.push_stop:
            deck.push_server.stop()
            print(json.dumps({"push_server": "stopped"}, indent=2))

    elif args.command == "flags":
        if args.list:
            print(json.dumps(deck.feature_flag_card(), indent=2))
        elif args.register:
            deck.feature_flags.register(args.register[0], enabled=args.register[1].lower() == "true")
            print(json.dumps({"registered": args.register[0]}, indent=2))
        elif args.set:
            deck.feature_flags.set(args.set[0], enabled=args.set[1].lower() == "true")
            print(json.dumps({"set": args.set[0]}, indent=2))
        elif args.check:
            print(json.dumps({"enabled": deck.feature_flags.is_enabled(args.check)}, indent=2))

    elif args.command == "config":
        if args.get:
            print(json.dumps({"value": deck.config.get(args.get)}, indent=2))
        elif args.set:
            deck.config.set(args.set[0], args.set[1])
            print(json.dumps({"set": args.set[0]}, indent=2))
        elif args.card:
            print(json.dumps(deck.config_card(), indent=2))
        elif args.reload:
            deck.config.reload()
            print(json.dumps({"reloaded": True}, indent=2))

    elif args.command == "schema":
        if args.register:
            deck.schema_registry.register(args.register[0], int(args.register[1]), {})
            print(json.dumps({"registered": args.register[0]}, indent=2))
        elif args.validate:
            data = json.loads(args.validate[1])
            errors = deck.schema_registry.validate(args.validate[0], data)
            print(json.dumps({"errors": errors}, indent=2))
        elif args.card:
            print(json.dumps(deck.schema_card(), indent=2))

    elif args.command == "secrets":
        if args.set:
            deck.secret_manager.set(args.set[0], args.set[1])
            print(json.dumps({"set": args.set[0]}, indent=2))
        elif args.get:
            print(json.dumps({"value": deck.secret_manager.get(args.get)}, indent=2))
        elif args.rotate:
            deck.secret_manager.rotate(args.rotate[0], args.rotate[1])
            print(json.dumps({"rotated": args.rotate[0]}, indent=2))
        elif args.card:
            print(json.dumps(deck.secret_card(), indent=2))

    elif args.command == "meta":
        if args.card:
            print(json.dumps(deck.meta_card(), indent=2))

    elif args.command == "dev":
        from skeleton.developer.cli import run_dev_cli
        result = run_dev_cli(args.args)
        if isinstance(result, dict):
            print(json.dumps(result, indent=2, default=str))
        sys.exit(0 if (isinstance(result, dict) and "error" not in result) else 1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
