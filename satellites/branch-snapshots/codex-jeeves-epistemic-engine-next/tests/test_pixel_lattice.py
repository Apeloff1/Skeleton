"""Tests for pixel lattice UI layout engine.

Covers cell creation, region definition, hit testing, and layout cards.
"""
from __future__ import annotations

import pytest

from skeleton.organism.pixel_lattice import (
    LatticeCell,
    PixelLattice,
    default_editor_lattice,
    default_hud_lattice,
    lattice_card,
)


class TestLatticeCell:
    def test_cell_creation(self):
        cell = LatticeCell(x=0, y=0, w=100, h=100, region="test")
        assert cell.x == 0
        assert cell.w == 100
        assert cell.region == "test"

    def test_contains(self):
        cell = LatticeCell(x=10, y=10, w=100, h=100, region="test")
        assert cell.contains(50, 50) is True
        assert cell.contains(5, 5) is False
        assert cell.contains(110, 110) is False
        assert cell.contains(10, 10) is True  # edge inclusive
        assert cell.contains(109, 109) is True
        assert cell.contains(110, 50) is False

    def test_center(self):
        cell = LatticeCell(x=0, y=0, w=100, h=200, region="test")
        assert cell.center() == (50, 100)

    def test_to_dict(self):
        cell = LatticeCell(x=0, y=0, w=100, h=100, region="test", z=5)
        d = cell.to_dict()
        assert d["region"] == "test"
        assert d["z"] == 5


class TestPixelLattice:
    def test_creation(self):
        lattice = PixelLattice(width=1920, height=1080, cols=24, rows=14)
        assert lattice.width == 1920
        assert lattice.cell_w == 80  # 1920 / 24

    def test_define_region(self):
        lattice = PixelLattice(width=100, height=100, cols=10, rows=10)
        cell = lattice.define_region("test", 0, 0, 5, 5)
        assert cell.w == 50  # 5 * 10
        assert cell.h == 50

    def test_regions(self):
        lattice = PixelLattice(width=100, height=100, cols=10, rows=10)
        lattice.define_region("a", 0, 0, 5, 5)
        lattice.define_region("b", 5, 0, 5, 5)
        assert sorted(lattice.regions()) == ["a", "b"]

    def test_cells_for(self):
        lattice = PixelLattice(width=100, height=100, cols=10, rows=10)
        lattice.define_region("a", 0, 0, 5, 5)
        cells = lattice.cells_for("a")
        assert len(cells) == 1
        assert cells[0].region == "a"

    def test_hit(self):
        lattice = PixelLattice(width=100, height=100, cols=10, rows=10)
        lattice.define_region("bg", 0, 0, 10, 10, z=0)
        lattice.define_region("fg", 2, 2, 4, 4, z=1)
        # Should hit foreground first due to higher z
        hit = lattice.hit(40, 40)
        assert hit is not None
        assert hit.region == "fg"

    def test_hit_miss(self):
        lattice = PixelLattice(width=100, height=100, cols=10, rows=10)
        lattice.define_region("test", 0, 0, 5, 5)
        hit = lattice.hit(60, 60)
        assert hit is None

    def test_to_dict(self):
        lattice = PixelLattice(width=100, height=100, cols=10, rows=10)
        lattice.define_region("test", 0, 0, 5, 5)
        d = lattice.to_dict()
        assert d["width"] == 100
        assert "test" in d["regions"]


class TestDefaultLayouts:
    def test_default_hud(self):
        lattice = default_hud_lattice()
        assert "viewport" in lattice.regions()
        assert "sidebar" in lattice.regions()
        assert "bottom_bar" in lattice.regions()
        assert "minimap" in lattice.regions()
        assert "overlay_alert" in lattice.regions()
        assert "tooltip" in lattice.regions()

    def test_default_editor(self):
        lattice = default_editor_lattice()
        assert "canvas" in lattice.regions()
        assert "properties" in lattice.regions()
        assert "timeline" in lattice.regions()
        assert "toolbar" in lattice.regions()
        assert "palette" in lattice.regions()

    def test_lattice_card(self):
        card = lattice_card()
        assert card["kind"] == "pixel-lattice-card"
        assert card["region_count"] > 0
        assert "viewport" in card["regions"]
