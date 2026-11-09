"""
Skeleton Package — Deployment and Configuration

Exports:
- Harness: Full-stack deployment orchestrator
- Config: Layered configuration system
- get_config(): Global configuration accessor
"""

from skeleton.config.system import Config, get_config, cfg
from skeleton.deploy.harness import Harness

__all__ = ["Harness", "Config", "get_config", "cfg"]
