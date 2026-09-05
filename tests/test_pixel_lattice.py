"""Tests for pixel lattice UI layout engine."""
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
    def test_contains_inside(self):
        cell = LatticeCell(x=0, y=0, w=100, h=100, region="test")
        assert cell.contains(50, 50) is True

    def test_contains_outside(self):
        cell = LatticeCell(x=0, y=0, w=100, h=100, region="test")
        assert cell.contains(150, 50) is False

    def test_contains_boundary(self):
        cell = LatticeCell(x=0, y=0, w=100, h=100, region="test")
        assert cell.contains(100, 100) is False  # exclusive upper bound
        assert cell.contains(0, 0) is True

    def test_center(self):
        cell = LatticeCell(x=0, y=0, w=100, h=200, region="test")
        assert cell.center() == (50, 100)

    def test_to_dict(self):
        cell = LatticeCell(x=10, y=20, w=30, h=40, region="r", z=5)
        d = cell.to_dict()
        assert d == {"x": 10, "y": 20, "w": 30, "h": 40, "region": "r", "z": 5}


class TestPixelLattice:
    def test_define_region(self):
        lattice = PixelLattice(width=1920, height=1080, cols=24, rows=14)
        cell = lattice.define_region("viewport", 0, 0, 18, 11, z=0)
        assert cell.region == "viewport"
        assert cell.w == 18 * (1920 // 24)
        assert cell.h == 11 * (1080 // 14)

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
        lattice.define_region("a", 0, 0, 5, 5, z=0)
        lattice.define_region("b", 0, 0, 5, 5, z=1)
        hit = lattice.hit(25, 25)
        assert hit is not None
        assert hit.region == "b"  # higher z wins

    def test_hit_none(self):
        lattice = PixelLattice(width=100, height=100, cols=10, rows=10)
        lattice.define_region("a", 0, 0, 5, 5)
        assert lattice.hit(95, 95) is None

    def test_to_dict(self):
        lattice = PixelLattice(width=100, height=100, cols=10, rows=10)
        lattice.define_region("a", 0, 0, 5, 5)
        d = lattice.to_dict()
        assert d["width"] == 100
        assert d["cols"] == 10
        assert "a" in d["regions"]


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

    def test_hud_viewport_size(self):
        lattice = default_hud_lattice()
        vp = lattice.cells_for("viewport")[0]
        assert vp.w == 18 * (1920 // 24)
        assert vp.h == 11 * (1080 // 14)


class TestLatticeCard:
    def test_card(self):
        lattice = default_hud_lattice()
        card = lattice_card(lattice)
        assert card["kind"] == "pixel-lattice-card"
        assert card["region_count"] == 6
        assert "viewport" in card["regions"]
