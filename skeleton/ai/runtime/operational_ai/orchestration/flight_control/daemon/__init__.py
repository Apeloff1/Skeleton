"""Single-backend, fail-closed native inference supervisor.

No provider fallback, automated recovery or model-controlled administrative work.
"""
from .contracts import DaemonPolicy,DaemonError,DaemonBusy,DaemonHeld
from .supervisor import InferenceDaemon
from .service import SupervisedFlightHTTP
__all__=['DaemonPolicy','DaemonError','DaemonBusy','DaemonHeld','InferenceDaemon','SupervisedFlightHTTP']
