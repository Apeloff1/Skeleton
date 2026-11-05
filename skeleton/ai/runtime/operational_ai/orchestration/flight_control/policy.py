"""Bounded admission counters for per-principal isolation and global pressure."""
from __future__ import annotations
from .contracts import FlightBusy,FlightPolicy


def enforce(conn,principal:str,policy:FlightPolicy)->None:
    queued=conn.execute("SELECT COUNT(*) FROM ai_flight_jobs WHERE state IN ('queued','claimed','running')").fetchone()[0]
    per=conn.execute("SELECT COUNT(*) FROM ai_flight_jobs WHERE principal=? AND state IN ('queued','claimed','running')",(principal,)).fetchone()[0]
    if queued>=policy.max_queued:raise FlightBusy('global queued admission ceiling')
    if per>=policy.max_per_principal:raise FlightBusy('principal queued admission ceiling')


def capacity(conn,policy:FlightPolicy)->None:
    running=conn.execute("SELECT COUNT(*) FROM ai_flight_jobs WHERE state='running'").fetchone()[0]
    claimed=conn.execute("SELECT COUNT(*) FROM ai_flight_jobs WHERE state='claimed'").fetchone()[0]
    if running>=policy.max_running:raise FlightBusy('active inference capacity exhausted')
    if claimed+running>=policy.max_claimed:raise FlightBusy('claim capacity exhausted')
