"""Compatibility shim for the canonical deployment strategies namespace."""
from skeleton.deploy.strategies.blue_green import BlueGreenDeployer, Environment, SwitchRecord

__all__ = ["BlueGreenDeployer", "Environment", "SwitchRecord"]
