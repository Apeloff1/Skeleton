"""Collision-free deterministic actor placement in a bounded occupancy grid."""
from ..contracts.errors import ContractError, ConflictError

def place(width: int, height: int, occupied: set[tuple[int, int]], *, seed: int) -> tuple[int, int]:
    if not 1 <= width <= 4096 or not 1 <= height <= 4096 or len(occupied) > width * height or (type(seed) is not int):
        raise ContractError('invalid grid')
    cells = width * height
    offset = seed % cells
    for step in range(cells):
        ordinal = (offset + step) % cells
        cell = (ordinal % width, ordinal // width)
        if cell not in occupied:
            return cell
    raise ConflictError('no unoccupied spawn cell')
