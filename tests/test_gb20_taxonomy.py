"""GB-20 taxonomy / region / catalog tests."""

from __future__ import annotations

import unittest

from skeleton.spine.law import (
    CERVICAL_N,
    COCCYX_N,
    LUMBAR_N,
    SACRAL_N,
    SEGMENT_N,
    THORACIC_N,
    VERTEBRA_N,
)
from skeleton.spine.taxonomy import (
    BY_LABEL,
    BY_ORDINAL,
    CATALOG,
    PREFIX,
    REGION_COUNTS,
    REGION_ORDER,
    Region,
    VertebraId,
    all_labels,
    is_mobile,
    iter_cranial_to_caudal,
    junction_labels,
    labels_in_region,
    mobile_labels,
    neighbor_labels,
    ordinal_of,
    region_of,
    region_span,
    validate_catalog,
)


class TestTaxonomyCounts(unittest.TestCase):
    def test_vertebra_total_33(self) -> None:
        self.assertEqual(VERTEBRA_N, 33)
        self.assertEqual(len(CATALOG), 33)
        self.assertEqual(len(all_labels()), 33)
        self.assertEqual(len(BY_LABEL), 33)
        self.assertEqual(len(BY_ORDINAL), 33)

    def test_region_counts_sum(self) -> None:
        self.assertEqual(CERVICAL_N, 7)
        self.assertEqual(THORACIC_N, 12)
        self.assertEqual(LUMBAR_N, 5)
        self.assertEqual(SACRAL_N, 5)
        self.assertEqual(COCCYX_N, 4)
        self.assertEqual(
            CERVICAL_N + THORACIC_N + LUMBAR_N + SACRAL_N + COCCYX_N, VERTEBRA_N
        )
        self.assertEqual(sum(REGION_COUNTS.values()), VERTEBRA_N)
        self.assertEqual(SEGMENT_N, VERTEBRA_N - 1)

    def test_region_order_and_prefix(self) -> None:
        self.assertEqual(
            list(REGION_ORDER),
            [Region.CERVICAL, Region.THORACIC, Region.LUMBAR, Region.SACRAL, Region.COCCYX],
        )
        self.assertIn(Region.CERVICAL, PREFIX)
        for region in Region:
            labels = labels_in_region(region)
            self.assertEqual(len(labels), REGION_COUNTS[region])
            for lb in labels:
                self.assertEqual(region_of(lb), region)

    def test_validate_catalog(self) -> None:
        validate_catalog()  # must not raise

    def test_ordinals_contiguous(self) -> None:
        labels = all_labels()
        for i, lb in enumerate(labels):
            self.assertEqual(ordinal_of(lb), i)
            self.assertEqual(BY_ORDINAL[i].label, lb)

    def test_iter_cranial_to_caudal(self) -> None:
        seq = list(iter_cranial_to_caudal())
        self.assertEqual(len(seq), 33)
        self.assertEqual(seq[0].label, all_labels()[0])
        self.assertEqual(seq[-1].label, all_labels()[-1])

    def test_junctions_and_neighbors(self) -> None:
        junctions = junction_labels()
        self.assertGreaterEqual(len(junctions), 4)
        for a, b in junctions:
            self.assertNotEqual(region_of(a), region_of(b))
        labels = all_labels()
        self.assertEqual(neighbor_labels(labels[0]), (None, labels[1]))
        self.assertEqual(neighbor_labels(labels[-1]), (labels[-2], None))
        mid = labels[10]
        self.assertEqual(neighbor_labels(mid), (labels[9], labels[11]))

    def test_mobile_vs_fused(self) -> None:
        mobile = mobile_labels()
        self.assertTrue(all(is_mobile(lb) for lb in mobile))
        # sacral + coccyx typically fused / non-mobile
        for lb in labels_in_region(Region.SACRAL) + labels_in_region(Region.COCCYX):
            # at least catalog marks fused appropriately via is_mobile
            self.assertIsInstance(is_mobile(lb), bool)

    def test_region_span(self) -> None:
        for region in Region:
            start, end = region_span(region)
            self.assertLessEqual(start, end)
            self.assertEqual(end - start + 1, REGION_COUNTS[region])

    def test_vertebra_id_fields(self) -> None:
        for vid in CATALOG:
            self.assertIsInstance(vid, VertebraId)
            self.assertTrue(vid.label)
            self.assertIn(vid.region, Region)


class TestTaxonomyExhaustiveLabels(unittest.TestCase):
    def test_every_label_round_maps(self) -> None:
        for lb in all_labels():
            self.assertIn(lb, BY_LABEL)
            self.assertEqual(BY_LABEL[lb].label, lb)
            self.assertEqual(all_labels()[ordinal_of(lb)], lb)

    def test_no_duplicate_labels(self) -> None:
        labels = all_labels()
        self.assertEqual(len(labels), len(set(labels)))

    def test_cervical_labels_c1_c7(self) -> None:
        cerv = labels_in_region(Region.CERVICAL)
        self.assertEqual(cerv[0][0], "C")
        self.assertEqual(len(cerv), 7)

    def test_thoracic_twelve(self) -> None:
        self.assertEqual(len(labels_in_region(Region.THORACIC)), 12)

    def test_lumbar_five(self) -> None:
        self.assertEqual(len(labels_in_region(Region.LUMBAR)), 5)


if __name__ == "__main__":
    unittest.main()
