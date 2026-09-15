"""Middleware package — request pipeline layers for the FastAPI backend.

Layers (wired up in server.py):
  security   — rate limiting, request audit ring buffer, body-size cap,
               path-traversal helper
  hardening  — per-path request timeouts, /api/health/detailed endpoint
"""
