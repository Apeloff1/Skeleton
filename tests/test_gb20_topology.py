"""GB-20 topology, dimensions, curvature, alignment, balance."""

from __future__ import annotations

import unittest

from skeleton.spine.alignment import (
    alignment_report,
    coronal_balance_ok,
    dual_plane_ok,
    sagittal_balance_ok,
)
from skeleton.spine.balance import balance_score, chain_com, support_polygon_ok
from skeleton.spine.chain import default_chain
from skeleton.spine.curvature import (
    apply_neutral_curves,
    cervical_lordosis,
    curvature_card_payload,
    curvature_sign_ok,
    lumbar_lordosis,
    thoracic_kyphosis,
)
from skeleton.spine.dimensions import (
    assert_monotonic_lumbar_widths,
    dims_for,
    region_height_mm,
    total_column_height_mm,
)
from skeleton.spine.law import SEGMENT_N, VERTEBRA_N
from skeleton.spine.taxonomy import BY_LABEL, Region, all_labels
from skeleton.spine.topology import (
    adjacency_list,
    connected_components,
    degree_map,
    has_cycle,
    is_connected,
    is_path_graph,
    path_distance,
    shortest_path,
    spine_graph,
    validate_topology,
)


class TestTopology(unittest.TestCase):
    def test_path_graph(self) -> None:
        g = spine_graph()
        self.assertEqual(len(g.vertices), VERTEBRA_N)
        self.assertEqual(len(g.edges), SEGMENT_N)
        self.assertTrue(is_path_graph())
        self.assertTrue(is_connected())
        self.assertFalse(has_cycle())
        comps = connected_components()
        self.assertEqual(len(comps), 1)
        self.assertEqual(len(comps[0]), VERTEBRA_N)

    def test_validate_topology(self) -> None:
        topo = validate_topology()
        self.assertEqual(topo["vertices"], 33)
        self.assertEqual(topo["edges"], 32)
        self.assertEqual(topo["components"], 1)

    def test_degrees_are_path_like(self) -> None:
        deg = degree_map()
        ends = [lb for lb, d in deg.items() if d == 1]
        mids = [lb for lb, d in deg.items() if d == 2]
        self.assertEqual(len(ends), 2)
        self.assertEqual(len(mids), 31)

    def test_shortest_path_span(self) -> None:
        labels = all_labels()
        path = shortest_path(labels[0], labels[-1])
        self.assertEqual(len(path), VERTEBRA_N)
        self.assertEqual(path_distance(labels[0], labels[-1]), VERTEBRA_N - 1)

    def test_adjacency(self) -> None:
        adj = adjacency_list()
        self.assertEqual(len(adj), VERTEBRA_N)


class TestDimensionsCurvatureAlignment(unittest.TestCase):
    def test_dimensions(self) -> None:
        self.assertGreater(total_column_height_mm(), 500.0)
        for region in Region:
            self.assertGreater(region_height_mm(region), 0.0)
        assert_monotonic_lumbar_widths()
        d = dims_for(BY_LABEL[all_labels()[0]])
        self.assertGreater(d.height_mm, 0.0)

    def test_neutral_curves_signs(self) -> None:
        chain = apply_neutral_curves(default_chain())
        self.assertTrue(curvature_sign_ok(chain))
        c = cervical_lordosis(chain)
        t = thoracic_kyphosis(chain)
        l = lumbar_lordosis(chain)
        self.assertLess(c.cobb_deg, 0.0)  # lordosis negative by convention here
        self.assertGreater(t.cobb_deg, 0.0)
        self.assertLess(l.cobb_deg, 0.0)
        payload = curvature_card_payload(chain)
        self.assertIn("cervical_cobb", payload)

    def test_alignment_and_balance(self) -> None:
        chain = default_chain()
        rep = alignment_report(chain)
        self.assertTrue(rep.ok)
        self.assertTrue(sagittal_balance_ok(chain))
        self.assertTrue(coronal_balance_ok(chain))
        self.assertTrue(dual_plane_ok(chain))
        self.assertGreaterEqual(balance_score(chain), 0.0)
        com = chain_com(chain)
        self.assertGreater(com.mass_g, 0.0)
        self.assertTrue(support_polygon_ok(chain))


if __name__ == "__main__":
    unittest.main()
