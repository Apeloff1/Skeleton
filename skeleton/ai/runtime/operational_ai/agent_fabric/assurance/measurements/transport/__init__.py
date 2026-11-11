"""Approved transport measurements and strict local lookup."""
ALLOWED=frozenset(('request_success_rate', 'unauthorized_requests', 'frame_bytes_ratio', 'connection_occupancy', 'stream_lag', 'cursor_age', 'event_delivery_rate', 'duplicate_delivery_ratio', 'throttle_fraction', 'disconnect_rate', 'heartbeat_age', 'client_poll_ratio'))
def measure(name,observations):
    if type(name) is not str or name not in ALLOWED:
        raise ValueError('unknown measurement contract')
    if name == "request_success_rate":
        from . import request_success_rate as module
    elif name == "unauthorized_requests":
        from . import unauthorized_requests as module
    elif name == "frame_bytes_ratio":
        from . import frame_bytes_ratio as module
    elif name == "connection_occupancy":
        from . import connection_occupancy as module
    elif name == "stream_lag":
        from . import stream_lag as module
    elif name == "cursor_age":
        from . import cursor_age as module
    elif name == "event_delivery_rate":
        from . import event_delivery_rate as module
    elif name == "duplicate_delivery_ratio":
        from . import duplicate_delivery_ratio as module
    elif name == "throttle_fraction":
        from . import throttle_fraction as module
    elif name == "disconnect_rate":
        from . import disconnect_rate as module
    elif name == "heartbeat_age":
        from . import heartbeat_age as module
    elif name == "client_poll_ratio":
        from . import client_poll_ratio as module
    else:
        raise ValueError('unknown measurement contract')
    return module.measure(observations)
