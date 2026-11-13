"""Canonical character movement interface for fixed-step gameplay."""
from .flgb_simulation_runtime import CharacterController, SimulationContractError
from .input_collision import MovementInput, MovementResult, step_character

__all__ = ["CharacterController", "SimulationContractError", "MovementInput", "MovementResult", "step_character"]
