"""One real model, one SQLite spine and one bounded loopback service."""
from __future__ import annotations
from contextlib import contextmanager
from typing import Iterator
from .contracts import DaemonPolicy
from .supervisor import InferenceDaemon

@contextmanager
def SupervisedFlightHTTP(application,knowledge,token,*,port:int=8766,
                         policy:DaemonPolicy|None=None):
    """Start the daemon and API only after same-model startup preflight succeeds.

    The model caller is background-owned; clients cannot invoke work_one. Calls
    to submit wake the worker after the queue transaction has committed.
    """
    from ....transport.flight.dispatch import FlightDispatcher
    from ....transport.flight.http import FlightHTTPServer
    with InferenceDaemon(application,policy=policy) as daemon:
        dispatcher=FlightDispatcher(application,knowledge_plane=knowledge,
                                    on_submit=daemon.notify,allow_manual_work=False,
                                    accepting=daemon.accepting)
        with FlightHTTPServer(('127.0.0.1',port),dispatcher,token,
                              supervisor=daemon) as server:
            yield server,daemon
