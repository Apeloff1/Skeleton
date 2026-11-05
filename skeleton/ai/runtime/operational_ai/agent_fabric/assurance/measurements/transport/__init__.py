"""Approved transport measurements and strict local lookup."""
from importlib import import_module
ALLOWED=frozenset(('request_success_rate', 'unauthorized_requests', 'frame_bytes_ratio', 'connection_occupancy', 'stream_lag', 'cursor_age', 'event_delivery_rate', 'duplicate_delivery_ratio', 'throttle_fraction', 'disconnect_rate', 'heartbeat_age', 'client_poll_ratio'))
def measure(name,observations):
    if name not in ALLOWED:raise ValueError('unknown measurement contract')
    module=import_module('skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.transport.'+name)
    return module.measure(observations)
