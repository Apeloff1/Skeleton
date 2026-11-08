"""Approved transport measurements and strict local lookup."""
from importlib import import_module
ALLOWED=frozenset(('request_success_rate', 'unauthorized_requests', 'frame_bytes_ratio', 'connection_occupancy', 'stream_lag', 'cursor_age', 'event_delivery_rate', 'duplicate_delivery_ratio', 'throttle_fraction', 'disconnect_rate', 'heartbeat_age', 'client_poll_ratio'))
_LOADERS = {
    "request_success_rate": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.transport.request_success_rate"),
    "unauthorized_requests": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.transport.unauthorized_requests"),
    "frame_bytes_ratio": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.transport.frame_bytes_ratio"),
    "connection_occupancy": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.transport.connection_occupancy"),
    "stream_lag": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.transport.stream_lag"),
    "cursor_age": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.transport.cursor_age"),
    "event_delivery_rate": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.transport.event_delivery_rate"),
    "duplicate_delivery_ratio": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.transport.duplicate_delivery_ratio"),
    "throttle_fraction": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.transport.throttle_fraction"),
    "disconnect_rate": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.transport.disconnect_rate"),
    "heartbeat_age": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.transport.heartbeat_age"),
    "client_poll_ratio": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.transport.client_poll_ratio"),
}

def measure(name,observations):
    if name not in ALLOWED:raise ValueError('unknown measurement contract')
    module=_LOADERS[name]()
    return module.measure(observations)
