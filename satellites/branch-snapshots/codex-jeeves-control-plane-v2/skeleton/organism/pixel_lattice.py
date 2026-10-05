"""UI pixel lattice — deterministic pixel-grid layout engine for UI surfaces.

Provides a coarse-to-fine grid system that maps logical UI regions to
pixel coordinates, enabling precise overlay rendering, hit-testing,
and responsive reflow without dynamic measurement.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class LatticeCell:
    x: int
    y: int
    w: int
    h: int
    region: str
    z: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h, "region": self.region, "z": self.z}

    def contains(self, px: int, py: int) -> bool:
        return self.x <= px < self.x + self.w and self.y <= py < self.y + self.h

    def center(self) -> Tuple[int, int]:
        return (self.x + self.w // 2, self.y + self.h // 2)


class PixelLattice:
    """A fixed-resolution grid decomposed into logical regions."""

    def __init__(self, width: int = 1920, height: int = 1080, cols: int = 24, rows: int = 14):
        self.width = width
        self.height = height
        self.cols = cols
        self.rows = rows
        self.cell_w = width // cols
        self.cell_h = height // rows
        self._cells: List[LatticeCell] = []
        self._region_index: Dict[str, List[LatticeCell]] = {}

    def define_region(self, name: str, col: int, row: int, colspan: int, rowspan: int, z: int = 0) -> LatticeCell:
        x = col * self.cell_w
        y = row * self.cell_h
        w = colspan * self.cell_w
        h = rowspan * self.cell_h
        cell = LatticeCell(x=x, y=y, w=w, h=h, region=name, z=z)
        self._cells.append(cell)
        self._region_index.setdefault(name, []).append(cell)
        return cell

    def regions(self) -> List[str]:
        return list(self._region_index.keys())

    def cells_for(self, region: str) -> List[LatticeCell]:
        return list(self._region_index.get(region, []))

    def hit(self, px: int, py: int) -> Optional[LatticeCell]:
        # Highest z first
        for cell in sorted(self._cells, key=lambda c: -c.z):
            if cell.contains(px, py):
                return cell
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "cols": self.cols,
            "rows": self.rows,
            "cell_w": self.cell_w,
            "cell_h": self.cell_h,
            "regions": {name: [c.to_dict() for c in cells] for name, cells in self._region_index.items()},
        }


def default_hud_lattice() -> PixelLattice:
    """Standard HUD layout: viewport, sidebar, bottom bar, minimap."""
    lattice = PixelLattice(width=1920, height=1080, cols=24, rows=14)
    lattice.define_region("viewport", 0, 0, 18, 11, z=0)
    lattice.define_region("sidebar", 18, 0, 6, 9, z=1)
    lattice.define_region("bottom_bar", 0, 11, 24, 3, z=2)
    lattice.define_region("minimap", 18, 9, 6, 2, z=3)
    lattice.define_region("overlay_alert", 6, 2, 12, 2, z=10)
    lattice.define_region("tooltip", 0, 0, 8, 2, z=11)
    return lattice


def default_editor_lattice() -> PixelLattice:
    """Editor layout: canvas left, property panel right, timeline bottom."""
    lattice = PixelLattice(width=1920, height=1080, cols=24, rows=14)
    lattice.define_region("canvas", 0, 0, 16, 10, z=0)
    lattice.define_region("properties", 16, 0, 8, 10, z=1)
    lattice.define_region("timeline", 0, 10, 24, 4, z=2)
    lattice.define_region("toolbar", 0, 0, 24, 1, z=5)
    lattice.define_region("palette", 16, 0, 8, 4, z=3)
    return lattice


def lattice_card(lattice: Optional[PixelLattice] = None) -> Dict[str, Any]:
    lat = lattice or default_hud_lattice()
    return {
        "kind": "pixel-lattice-card",
        "layout": lat.to_dict(),
        "region_count": len(lat.regions()),
        "regions": lat.regions(),
        "stored_prose": 0,
    }
