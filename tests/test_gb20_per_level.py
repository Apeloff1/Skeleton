"""GB-20 per-level exhaustive taxonomy/dimensions/vertebra checks."""

from __future__ import annotations

import unittest

from skeleton.spine.dimensions import (
    CATALOG as DIM_CATALOG,
    all_dims,
    dims_by_label,
    dims_for,
    mass_proxy_g,
    region_height_mm,
    total_column_height_mm,
)
from skeleton.spine.law import SEGMENT_N, VERTEBRA_N
from skeleton.spine.segment import (
    build_segments,
    mean_axial_stiffness,
    mobile_segments,
    segment_by_label,
    segment_index_of,
    total_disc_height_mm,
)
from skeleton.spine.taxonomy import (
    BY_LABEL,
    Region,
    all_labels,
    is_mobile,
    labels_in_region,
    neighbor_labels,
    ordinal_of,
    region_of,
)
from skeleton.spine.vertebra import (
    ZERO_POSE,
    by_label,
    default_column,
    filter_region,
    make_vertebra,
    mobile_subset,
    pose_energy,
)


class TestPerVertebraExhaustive(unittest.TestCase):

    def test_vertebra_slot_00(self) -> None:
        labels = all_labels()
        lb = labels[0]
        self.assertEqual(ordinal_of(lb), 0)
        col = default_column()
        v = col[0]
        self.assertEqual(v.label, lb)
        self.assertEqual(v.pose.as_tuple(), ZERO_POSE.as_tuple())
        d = dims_for(BY_LABEL[lb])
        self.assertGreater(d.height_mm, 0.0)
        self.assertGreater(d.width_mm, 0.0)
        self.assertGreater(mass_proxy_g(lb), 0.0)
        prev, nxt = neighbor_labels(lb)
        if 0 == 0:
            self.assertIsNone(prev)
            self.assertEqual(nxt, labels[1])
        elif 0 == 32:
            self.assertEqual(prev, labels[31])
            self.assertIsNone(nxt)
        else:
            self.assertEqual(prev, labels[0 - 1])
            self.assertEqual(nxt, labels[0 + 1])
        rebuilt = make_vertebra(lb)
        self.assertEqual(rebuilt.label, lb)
        self.assertIsInstance(is_mobile(lb), bool)

    def test_vertebra_slot_01(self) -> None:
        labels = all_labels()
        lb = labels[1]
        self.assertEqual(ordinal_of(lb), 1)
        col = default_column()
        v = col[1]
        self.assertEqual(v.label, lb)
        self.assertEqual(v.pose.as_tuple(), ZERO_POSE.as_tuple())
        d = dims_for(BY_LABEL[lb])
        self.assertGreater(d.height_mm, 0.0)
        self.assertGreater(d.width_mm, 0.0)
        self.assertGreater(mass_proxy_g(lb), 0.0)
        prev, nxt = neighbor_labels(lb)
        if 1 == 0:
            self.assertIsNone(prev)
            self.assertEqual(nxt, labels[1])
        elif 1 == 32:
            self.assertEqual(prev, labels[31])
            self.assertIsNone(nxt)
        else:
            self.assertEqual(prev, labels[1 - 1])
            self.assertEqual(nxt, labels[1 + 1])
        rebuilt = make_vertebra(lb)
        self.assertEqual(rebuilt.label, lb)
        self.assertIsInstance(is_mobile(lb), bool)

    def test_vertebra_slot_02(self) -> None:
        labels = all_labels()
        lb = labels[2]
        self.assertEqual(ordinal_of(lb), 2)
        col = default_column()
        v = col[2]
        self.assertEqual(v.label, lb)
        self.assertEqual(v.pose.as_tuple(), ZERO_POSE.as_tuple())
        d = dims_for(BY_LABEL[lb])
        self.assertGreater(d.height_mm, 0.0)
        self.assertGreater(d.width_mm, 0.0)
        self.assertGreater(mass_proxy_g(lb), 0.0)
        prev, nxt = neighbor_labels(lb)
        if 2 == 0:
            self.assertIsNone(prev)
            self.assertEqual(nxt, labels[1])
        elif 2 == 32:
            self.assertEqual(prev, labels[31])
            self.assertIsNone(nxt)
        else:
            self.assertEqual(prev, labels[2 - 1])
            self.assertEqual(nxt, labels[2 + 1])
        rebuilt = make_vertebra(lb)
        self.assertEqual(rebuilt.label, lb)
        self.assertIsInstance(is_mobile(lb), bool)

    def test_vertebra_slot_03(self) -> None:
        labels = all_labels()
        lb = labels[3]
        self.assertEqual(ordinal_of(lb), 3)
        col = default_column()
        v = col[3]
        self.assertEqual(v.label, lb)
        self.assertEqual(v.pose.as_tuple(), ZERO_POSE.as_tuple())
        d = dims_for(BY_LABEL[lb])
        self.assertGreater(d.height_mm, 0.0)
        self.assertGreater(d.width_mm, 0.0)
        self.assertGreater(mass_proxy_g(lb), 0.0)
        prev, nxt = neighbor_labels(lb)
        if 3 == 0:
            self.assertIsNone(prev)
            self.assertEqual(nxt, labels[1])
        elif 3 == 32:
            self.assertEqual(prev, labels[31])
            self.assertIsNone(nxt)
        else:
            self.assertEqual(prev, labels[3 - 1])
            self.assertEqual(nxt, labels[3 + 1])
        rebuilt = make_vertebra(lb)
        self.assertEqual(rebuilt.label, lb)
        self.assertIsInstance(is_mobile(lb), bool)

    def test_vertebra_slot_04(self) -> None:
        labels = all_labels()
        lb = labels[4]
        self.assertEqual(ordinal_of(lb), 4)
        col = default_column()
        v = col[4]
        self.assertEqual(v.label, lb)
        self.assertEqual(v.pose.as_tuple(), ZERO_POSE.as_tuple())
        d = dims_for(BY_LABEL[lb])
        self.assertGreater(d.height_mm, 0.0)
        self.assertGreater(d.width_mm, 0.0)
        self.assertGreater(mass_proxy_g(lb), 0.0)
        prev, nxt = neighbor_labels(lb)
        if 4 == 0:
            self.assertIsNone(prev)
            self.assertEqual(nxt, labels[1])
        elif 4 == 32:
            self.assertEqual(prev, labels[31])
            self.assertIsNone(nxt)
        else:
            self.assertEqual(prev, labels[4 - 1])
            self.assertEqual(nxt, labels[4 + 1])
        rebuilt = make_vertebra(lb)
        self.assertEqual(rebuilt.label, lb)
        self.assertIsInstance(is_mobile(lb), bool)

    def test_vertebra_slot_05(self) -> None:
        labels = all_labels()
        lb = labels[5]
        self.assertEqual(ordinal_of(lb), 5)
        col = default_column()
        v = col[5]
        self.assertEqual(v.label, lb)
        self.assertEqual(v.pose.as_tuple(), ZERO_POSE.as_tuple())
        d = dims_for(BY_LABEL[lb])
        self.assertGreater(d.height_mm, 0.0)
        self.assertGreater(d.width_mm, 0.0)
        self.assertGreater(mass_proxy_g(lb), 0.0)
        prev, nxt = neighbor_labels(lb)
        if 5 == 0:
            self.assertIsNone(prev)
            self.assertEqual(nxt, labels[1])
        elif 5 == 32:
            self.assertEqual(prev, labels[31])
            self.assertIsNone(nxt)
        else:
            self.assertEqual(prev, labels[5 - 1])
            self.assertEqual(nxt, labels[5 + 1])
        rebuilt = make_vertebra(lb)
        self.assertEqual(rebuilt.label, lb)
        self.assertIsInstance(is_mobile(lb), bool)

    def test_vertebra_slot_06(self) -> None:
        labels = all_labels()
        lb = labels[6]
        self.assertEqual(ordinal_of(lb), 6)
        col = default_column()
        v = col[6]
        self.assertEqual(v.label, lb)
        self.assertEqual(v.pose.as_tuple(), ZERO_POSE.as_tuple())
        d = dims_for(BY_LABEL[lb])
        self.assertGreater(d.height_mm, 0.0)
        self.assertGreater(d.width_mm, 0.0)
        self.assertGreater(mass_proxy_g(lb), 0.0)
        prev, nxt = neighbor_labels(lb)
        if 6 == 0:
            self.assertIsNone(prev)
            self.assertEqual(nxt, labels[1])
        elif 6 == 32:
            self.assertEqual(prev, labels[31])
            self.assertIsNone(nxt)
        else:
            self.assertEqual(prev, labels[6 - 1])
            self.assertEqual(nxt, labels[6 + 1])
        rebuilt = make_vertebra(lb)
        self.assertEqual(rebuilt.label, lb)
        self.assertIsInstance(is_mobile(lb), bool)

    def test_vertebra_slot_07(self) -> None:
        labels = all_labels()
        lb = labels[7]
        self.assertEqual(ordinal_of(lb), 7)
        col = default_column()
        v = col[7]
        self.assertEqual(v.label, lb)
        self.assertEqual(v.pose.as_tuple(), ZERO_POSE.as_tuple())
        d = dims_for(BY_LABEL[lb])
        self.assertGreater(d.height_mm, 0.0)
        self.assertGreater(d.width_mm, 0.0)
        self.assertGreater(mass_proxy_g(lb), 0.0)
        prev, nxt = neighbor_labels(lb)
        if 7 == 0:
            self.assertIsNone(prev)
            self.assertEqual(nxt, labels[1])
        elif 7 == 32:
            self.assertEqual(prev, labels[31])
            self.assertIsNone(nxt)
        else:
            self.assertEqual(prev, labels[7 - 1])
            self.assertEqual(nxt, labels[7 + 1])
        rebuilt = make_vertebra(lb)
        self.assertEqual(rebuilt.label, lb)
        self.assertIsInstance(is_mobile(lb), bool)

    def test_vertebra_slot_08(self) -> None:
        labels = all_labels()
        lb = labels[8]
        self.assertEqual(ordinal_of(lb), 8)
        col = default_column()
        v = col[8]
        self.assertEqual(v.label, lb)
        self.assertEqual(v.pose.as_tuple(), ZERO_POSE.as_tuple())
        d = dims_for(BY_LABEL[lb])
        self.assertGreater(d.height_mm, 0.0)
        self.assertGreater(d.width_mm, 0.0)
        self.assertGreater(mass_proxy_g(lb), 0.0)
        prev, nxt = neighbor_labels(lb)
        if 8 == 0:
            self.assertIsNone(prev)
            self.assertEqual(nxt, labels[1])
        elif 8 == 32:
            self.assertEqual(prev, labels[31])
            self.assertIsNone(nxt)
        else:
            self.assertEqual(prev, labels[8 - 1])
            self.assertEqual(nxt, labels[8 + 1])
        rebuilt = make_vertebra(lb)
        self.assertEqual(rebuilt.label, lb)
        self.assertIsInstance(is_mobile(lb), bool)

    def test_vertebra_slot_09(self) -> None:
        labels = all_labels()
        lb = labels[9]
        self.assertEqual(ordinal_of(lb), 9)
        col = default_column()
        v = col[9]
        self.assertEqual(v.label, lb)
        self.assertEqual(v.pose.as_tuple(), ZERO_POSE.as_tuple())
        d = dims_for(BY_LABEL[lb])
        self.assertGreater(d.height_mm, 0.0)
        self.assertGreater(d.width_mm, 0.0)
        self.assertGreater(mass_proxy_g(lb), 0.0)
        prev, nxt = neighbor_labels(lb)
        if 9 == 0:
            self.assertIsNone(prev)
            self.assertEqual(nxt, labels[1])
        elif 9 == 32:
            self.assertEqual(prev, labels[31])
            self.assertIsNone(nxt)
        else:
            self.assertEqual(prev, labels[9 - 1])
            self.assertEqual(nxt, labels[9 + 1])
        rebuilt = make_vertebra(lb)
        self.assertEqual(rebuilt.label, lb)
        self.assertIsInstance(is_mobile(lb), bool)

    def test_vertebra_slot_10(self) -> None:
        labels = all_labels()
        lb = labels[10]
        self.assertEqual(ordinal_of(lb), 10)
        col = default_column()
        v = col[10]
        self.assertEqual(v.label, lb)
        self.assertEqual(v.pose.as_tuple(), ZERO_POSE.as_tuple())
        d = dims_for(BY_LABEL[lb])
        self.assertGreater(d.height_mm, 0.0)
        self.assertGreater(d.width_mm, 0.0)
        self.assertGreater(mass_proxy_g(lb), 0.0)
        prev, nxt = neighbor_labels(lb)
        if 10 == 0:
            self.assertIsNone(prev)
            self.assertEqual(nxt, labels[1])
        elif 10 == 32:
            self.assertEqual(prev, labels[31])
            self.assertIsNone(nxt)
        else:
            self.assertEqual(prev, labels[10 - 1])
            self.assertEqual(nxt, labels[10 + 1])
        rebuilt = make_vertebra(lb)
        self.assertEqual(rebuilt.label, lb)
        self.assertIsInstance(is_mobile(lb), bool)

    def test_vertebra_slot_11(self) -> None:
        labels = all_labels()
        lb = labels[11]
        self.assertEqual(ordinal_of(lb), 11)
        col = default_column()
        v = col[11]
        self.assertEqual(v.label, lb)
        self.assertEqual(v.pose.as_tuple(), ZERO_POSE.as_tuple())
        d = dims_for(BY_LABEL[lb])
        self.assertGreater(d.height_mm, 0.0)
        self.assertGreater(d.width_mm, 0.0)
        self.assertGreater(mass_proxy_g(lb), 0.0)
        prev, nxt = neighbor_labels(lb)
        if 11 == 0:
            self.assertIsNone(prev)
            self.assertEqual(nxt, labels[1])
        elif 11 == 32:
            self.assertEqual(prev, labels[31])
            self.assertIsNone(nxt)
        else:
            self.assertEqual(prev, labels[11 - 1])
            self.assertEqual(nxt, labels[11 + 1])
        rebuilt = make_vertebra(lb)
        self.assertEqual(rebuilt.label, lb)
        self.assertIsInstance(is_mobile(lb), bool)

    def test_vertebra_slot_12(self) -> None:
        labels = all_labels()
        lb = labels[12]
        self.assertEqual(ordinal_of(lb), 12)
        col = default_column()
        v = col[12]
        self.assertEqual(v.label, lb)
        self.assertEqual(v.pose.as_tuple(), ZERO_POSE.as_tuple())
        d = dims_for(BY_LABEL[lb])
        self.assertGreater(d.height_mm, 0.0)
        self.assertGreater(d.width_mm, 0.0)
        self.assertGreater(mass_proxy_g(lb), 0.0)
        prev, nxt = neighbor_labels(lb)
        if 12 == 0:
            self.assertIsNone(prev)
            self.assertEqual(nxt, labels[1])
        elif 12 == 32:
            self.assertEqual(prev, labels[31])
            self.assertIsNone(nxt)
        else:
            self.assertEqual(prev, labels[12 - 1])
            self.assertEqual(nxt, labels[12 + 1])
        rebuilt = make_vertebra(lb)
        self.assertEqual(rebuilt.label, lb)
        self.assertIsInstance(is_mobile(lb), bool)

    def test_vertebra_slot_13(self) -> None:
        labels = all_labels()
        lb = labels[13]
        self.assertEqual(ordinal_of(lb), 13)
        col = default_column()
        v = col[13]
        self.assertEqual(v.label, lb)
        self.assertEqual(v.pose.as_tuple(), ZERO_POSE.as_tuple())
        d = dims_for(BY_LABEL[lb])
        self.assertGreater(d.height_mm, 0.0)
        self.assertGreater(d.width_mm, 0.0)
        self.assertGreater(mass_proxy_g(lb), 0.0)
        prev, nxt = neighbor_labels(lb)
        if 13 == 0:
            self.assertIsNone(prev)
            self.assertEqual(nxt, labels[1])
        elif 13 == 32:
            self.assertEqual(prev, labels[31])
            self.assertIsNone(nxt)
        else:
            self.assertEqual(prev, labels[13 - 1])
            self.assertEqual(nxt, labels[13 + 1])
        rebuilt = make_vertebra(lb)
        self.assertEqual(rebuilt.label, lb)
        self.assertIsInstance(is_mobile(lb), bool)

    def test_vertebra_slot_14(self) -> None:
        labels = all_labels()
        lb = labels[14]
        self.assertEqual(ordinal_of(lb), 14)
        col = default_column()
        v = col[14]
        self.assertEqual(v.label, lb)
        self.assertEqual(v.pose.as_tuple(), ZERO_POSE.as_tuple())
        d = dims_for(BY_LABEL[lb])
        self.assertGreater(d.height_mm, 0.0)
        self.assertGreater(d.width_mm, 0.0)
        self.assertGreater(mass_proxy_g(lb), 0.0)
        prev, nxt = neighbor_labels(lb)
        if 14 == 0:
            self.assertIsNone(prev)
            self.assertEqual(nxt, labels[1])
        elif 14 == 32:
            self.assertEqual(prev, labels[31])
            self.assertIsNone(nxt)
        else:
            self.assertEqual(prev, labels[14 - 1])
            self.assertEqual(nxt, labels[14 + 1])
        rebuilt = make_vertebra(lb)
        self.assertEqual(rebuilt.label, lb)
        self.assertIsInstance(is_mobile(lb), bool)

    def test_vertebra_slot_15(self) -> None:
        labels = all_labels()
        lb = labels[15]
        self.assertEqual(ordinal_of(lb), 15)
        col = default_column()
        v = col[15]
        self.assertEqual(v.label, lb)
        self.assertEqual(v.pose.as_tuple(), ZERO_POSE.as_tuple())
        d = dims_for(BY_LABEL[lb])
        self.assertGreater(d.height_mm, 0.0)
        self.assertGreater(d.width_mm, 0.0)
        self.assertGreater(mass_proxy_g(lb), 0.0)
        prev, nxt = neighbor_labels(lb)
        if 15 == 0:
            self.assertIsNone(prev)
            self.assertEqual(nxt, labels[1])
        elif 15 == 32:
            self.assertEqual(prev, labels[31])
            self.assertIsNone(nxt)
        else:
            self.assertEqual(prev, labels[15 - 1])
            self.assertEqual(nxt, labels[15 + 1])
        rebuilt = make_vertebra(lb)
        self.assertEqual(rebuilt.label, lb)
        self.assertIsInstance(is_mobile(lb), bool)

    def test_vertebra_slot_16(self) -> None:
        labels = all_labels()
        lb = labels[16]
        self.assertEqual(ordinal_of(lb), 16)
        col = default_column()
        v = col[16]
        self.assertEqual(v.label, lb)
        self.assertEqual(v.pose.as_tuple(), ZERO_POSE.as_tuple())
        d = dims_for(BY_LABEL[lb])
        self.assertGreater(d.height_mm, 0.0)
        self.assertGreater(d.width_mm, 0.0)
        self.assertGreater(mass_proxy_g(lb), 0.0)
        prev, nxt = neighbor_labels(lb)
        if 16 == 0:
            self.assertIsNone(prev)
            self.assertEqual(nxt, labels[1])
        elif 16 == 32:
            self.assertEqual(prev, labels[31])
            self.assertIsNone(nxt)
        else:
            self.assertEqual(prev, labels[16 - 1])
            self.assertEqual(nxt, labels[16 + 1])
        rebuilt = make_vertebra(lb)
        self.assertEqual(rebuilt.label, lb)
        self.assertIsInstance(is_mobile(lb), bool)

    def test_vertebra_slot_17(self) -> None:
        labels = all_labels()
        lb = labels[17]
        self.assertEqual(ordinal_of(lb), 17)
        col = default_column()
        v = col[17]
        self.assertEqual(v.label, lb)
        self.assertEqual(v.pose.as_tuple(), ZERO_POSE.as_tuple())
        d = dims_for(BY_LABEL[lb])
        self.assertGreater(d.height_mm, 0.0)
        self.assertGreater(d.width_mm, 0.0)
        self.assertGreater(mass_proxy_g(lb), 0.0)
        prev, nxt = neighbor_labels(lb)
        if 17 == 0:
            self.assertIsNone(prev)
            self.assertEqual(nxt, labels[1])
        elif 17 == 32:
            self.assertEqual(prev, labels[31])
            self.assertIsNone(nxt)
        else:
            self.assertEqual(prev, labels[17 - 1])
            self.assertEqual(nxt, labels[17 + 1])
        rebuilt = make_vertebra(lb)
        self.assertEqual(rebuilt.label, lb)
        self.assertIsInstance(is_mobile(lb), bool)

    def test_vertebra_slot_18(self) -> None:
        labels = all_labels()
        lb = labels[18]
        self.assertEqual(ordinal_of(lb), 18)
        col = default_column()
        v = col[18]
        self.assertEqual(v.label, lb)
        self.assertEqual(v.pose.as_tuple(), ZERO_POSE.as_tuple())
        d = dims_for(BY_LABEL[lb])
        self.assertGreater(d.height_mm, 0.0)
        self.assertGreater(d.width_mm, 0.0)
        self.assertGreater(mass_proxy_g(lb), 0.0)
        prev, nxt = neighbor_labels(lb)
        if 18 == 0:
            self.assertIsNone(prev)
            self.assertEqual(nxt, labels[1])
        elif 18 == 32:
            self.assertEqual(prev, labels[31])
            self.assertIsNone(nxt)
        else:
            self.assertEqual(prev, labels[18 - 1])
            self.assertEqual(nxt, labels[18 + 1])
        rebuilt = make_vertebra(lb)
        self.assertEqual(rebuilt.label, lb)
        self.assertIsInstance(is_mobile(lb), bool)

    def test_vertebra_slot_19(self) -> None:
        labels = all_labels()
        lb = labels[19]
        self.assertEqual(ordinal_of(lb), 19)
        col = default_column()
        v = col[19]
        self.assertEqual(v.label, lb)
        self.assertEqual(v.pose.as_tuple(), ZERO_POSE.as_tuple())
        d = dims_for(BY_LABEL[lb])
        self.assertGreater(d.height_mm, 0.0)
        self.assertGreater(d.width_mm, 0.0)
        self.assertGreater(mass_proxy_g(lb), 0.0)
        prev, nxt = neighbor_labels(lb)
        if 19 == 0:
            self.assertIsNone(prev)
            self.assertEqual(nxt, labels[1])
        elif 19 == 32:
            self.assertEqual(prev, labels[31])
            self.assertIsNone(nxt)
        else:
            self.assertEqual(prev, labels[19 - 1])
            self.assertEqual(nxt, labels[19 + 1])
        rebuilt = make_vertebra(lb)
        self.assertEqual(rebuilt.label, lb)
        self.assertIsInstance(is_mobile(lb), bool)

    def test_vertebra_slot_20(self) -> None:
        labels = all_labels()
        lb = labels[20]
        self.assertEqual(ordinal_of(lb), 20)
        col = default_column()
        v = col[20]
        self.assertEqual(v.label, lb)
        self.assertEqual(v.pose.as_tuple(), ZERO_POSE.as_tuple())
        d = dims_for(BY_LABEL[lb])
        self.assertGreater(d.height_mm, 0.0)
        self.assertGreater(d.width_mm, 0.0)
        self.assertGreater(mass_proxy_g(lb), 0.0)
        prev, nxt = neighbor_labels(lb)
        if 20 == 0:
            self.assertIsNone(prev)
            self.assertEqual(nxt, labels[1])
        elif 20 == 32:
            self.assertEqual(prev, labels[31])
            self.assertIsNone(nxt)
        else:
            self.assertEqual(prev, labels[20 - 1])
            self.assertEqual(nxt, labels[20 + 1])
        rebuilt = make_vertebra(lb)
        self.assertEqual(rebuilt.label, lb)
        self.assertIsInstance(is_mobile(lb), bool)

    def test_vertebra_slot_21(self) -> None:
        labels = all_labels()
        lb = labels[21]
        self.assertEqual(ordinal_of(lb), 21)
        col = default_column()
        v = col[21]
        self.assertEqual(v.label, lb)
        self.assertEqual(v.pose.as_tuple(), ZERO_POSE.as_tuple())
        d = dims_for(BY_LABEL[lb])
        self.assertGreater(d.height_mm, 0.0)
        self.assertGreater(d.width_mm, 0.0)
        self.assertGreater(mass_proxy_g(lb), 0.0)
        prev, nxt = neighbor_labels(lb)
        if 21 == 0:
            self.assertIsNone(prev)
            self.assertEqual(nxt, labels[1])
        elif 21 == 32:
            self.assertEqual(prev, labels[31])
            self.assertIsNone(nxt)
        else:
            self.assertEqual(prev, labels[21 - 1])
            self.assertEqual(nxt, labels[21 + 1])
        rebuilt = make_vertebra(lb)
        self.assertEqual(rebuilt.label, lb)
        self.assertIsInstance(is_mobile(lb), bool)

    def test_vertebra_slot_22(self) -> None:
        labels = all_labels()
        lb = labels[22]
        self.assertEqual(ordinal_of(lb), 22)
        col = default_column()
        v = col[22]
        self.assertEqual(v.label, lb)
        self.assertEqual(v.pose.as_tuple(), ZERO_POSE.as_tuple())
        d = dims_for(BY_LABEL[lb])
        self.assertGreater(d.height_mm, 0.0)
        self.assertGreater(d.width_mm, 0.0)
        self.assertGreater(mass_proxy_g(lb), 0.0)
        prev, nxt = neighbor_labels(lb)
        if 22 == 0:
            self.assertIsNone(prev)
            self.assertEqual(nxt, labels[1])
        elif 22 == 32:
            self.assertEqual(prev, labels[31])
            self.assertIsNone(nxt)
        else:
            self.assertEqual(prev, labels[22 - 1])
            self.assertEqual(nxt, labels[22 + 1])
        rebuilt = make_vertebra(lb)
        self.assertEqual(rebuilt.label, lb)
        self.assertIsInstance(is_mobile(lb), bool)

    def test_vertebra_slot_23(self) -> None:
        labels = all_labels()
        lb = labels[23]
        self.assertEqual(ordinal_of(lb), 23)
        col = default_column()
        v = col[23]
        self.assertEqual(v.label, lb)
        self.assertEqual(v.pose.as_tuple(), ZERO_POSE.as_tuple())
        d = dims_for(BY_LABEL[lb])
        self.assertGreater(d.height_mm, 0.0)
        self.assertGreater(d.width_mm, 0.0)
        self.assertGreater(mass_proxy_g(lb), 0.0)
        prev, nxt = neighbor_labels(lb)
        if 23 == 0:
            self.assertIsNone(prev)
            self.assertEqual(nxt, labels[1])
        elif 23 == 32:
            self.assertEqual(prev, labels[31])
            self.assertIsNone(nxt)
        else:
            self.assertEqual(prev, labels[23 - 1])
            self.assertEqual(nxt, labels[23 + 1])
        rebuilt = make_vertebra(lb)
        self.assertEqual(rebuilt.label, lb)
        self.assertIsInstance(is_mobile(lb), bool)

    def test_vertebra_slot_24(self) -> None:
        labels = all_labels()
        lb = labels[24]
        self.assertEqual(ordinal_of(lb), 24)
        col = default_column()
        v = col[24]
        self.assertEqual(v.label, lb)
        self.assertEqual(v.pose.as_tuple(), ZERO_POSE.as_tuple())
        d = dims_for(BY_LABEL[lb])
        self.assertGreater(d.height_mm, 0.0)
        self.assertGreater(d.width_mm, 0.0)
        self.assertGreater(mass_proxy_g(lb), 0.0)
        prev, nxt = neighbor_labels(lb)
        if 24 == 0:
            self.assertIsNone(prev)
            self.assertEqual(nxt, labels[1])
        elif 24 == 32:
            self.assertEqual(prev, labels[31])
            self.assertIsNone(nxt)
        else:
            self.assertEqual(prev, labels[24 - 1])
            self.assertEqual(nxt, labels[24 + 1])
        rebuilt = make_vertebra(lb)
        self.assertEqual(rebuilt.label, lb)
        self.assertIsInstance(is_mobile(lb), bool)

    def test_vertebra_slot_25(self) -> None:
        labels = all_labels()
        lb = labels[25]
        self.assertEqual(ordinal_of(lb), 25)
        col = default_column()
        v = col[25]
        self.assertEqual(v.label, lb)
        self.assertEqual(v.pose.as_tuple(), ZERO_POSE.as_tuple())
        d = dims_for(BY_LABEL[lb])
        self.assertGreater(d.height_mm, 0.0)
        self.assertGreater(d.width_mm, 0.0)
        self.assertGreater(mass_proxy_g(lb), 0.0)
        prev, nxt = neighbor_labels(lb)
        if 25 == 0:
            self.assertIsNone(prev)
            self.assertEqual(nxt, labels[1])
        elif 25 == 32:
            self.assertEqual(prev, labels[31])
            self.assertIsNone(nxt)
        else:
            self.assertEqual(prev, labels[25 - 1])
            self.assertEqual(nxt, labels[25 + 1])
        rebuilt = make_vertebra(lb)
        self.assertEqual(rebuilt.label, lb)
        self.assertIsInstance(is_mobile(lb), bool)

    def test_vertebra_slot_26(self) -> None:
        labels = all_labels()
        lb = labels[26]
        self.assertEqual(ordinal_of(lb), 26)
        col = default_column()
        v = col[26]
        self.assertEqual(v.label, lb)
        self.assertEqual(v.pose.as_tuple(), ZERO_POSE.as_tuple())
        d = dims_for(BY_LABEL[lb])
        self.assertGreater(d.height_mm, 0.0)
        self.assertGreater(d.width_mm, 0.0)
        self.assertGreater(mass_proxy_g(lb), 0.0)
        prev, nxt = neighbor_labels(lb)
        if 26 == 0:
            self.assertIsNone(prev)
            self.assertEqual(nxt, labels[1])
        elif 26 == 32:
            self.assertEqual(prev, labels[31])
            self.assertIsNone(nxt)
        else:
            self.assertEqual(prev, labels[26 - 1])
            self.assertEqual(nxt, labels[26 + 1])
        rebuilt = make_vertebra(lb)
        self.assertEqual(rebuilt.label, lb)
        self.assertIsInstance(is_mobile(lb), bool)

    def test_vertebra_slot_27(self) -> None:
        labels = all_labels()
        lb = labels[27]
        self.assertEqual(ordinal_of(lb), 27)
        col = default_column()
        v = col[27]
        self.assertEqual(v.label, lb)
        self.assertEqual(v.pose.as_tuple(), ZERO_POSE.as_tuple())
        d = dims_for(BY_LABEL[lb])
        self.assertGreater(d.height_mm, 0.0)
        self.assertGreater(d.width_mm, 0.0)
        self.assertGreater(mass_proxy_g(lb), 0.0)
        prev, nxt = neighbor_labels(lb)
        if 27 == 0:
            self.assertIsNone(prev)
            self.assertEqual(nxt, labels[1])
        elif 27 == 32:
            self.assertEqual(prev, labels[31])
            self.assertIsNone(nxt)
        else:
            self.assertEqual(prev, labels[27 - 1])
            self.assertEqual(nxt, labels[27 + 1])
        rebuilt = make_vertebra(lb)
        self.assertEqual(rebuilt.label, lb)
        self.assertIsInstance(is_mobile(lb), bool)

    def test_vertebra_slot_28(self) -> None:
        labels = all_labels()
        lb = labels[28]
        self.assertEqual(ordinal_of(lb), 28)
        col = default_column()
        v = col[28]
        self.assertEqual(v.label, lb)
        self.assertEqual(v.pose.as_tuple(), ZERO_POSE.as_tuple())
        d = dims_for(BY_LABEL[lb])
        self.assertGreater(d.height_mm, 0.0)
        self.assertGreater(d.width_mm, 0.0)
        self.assertGreater(mass_proxy_g(lb), 0.0)
        prev, nxt = neighbor_labels(lb)
        if 28 == 0:
            self.assertIsNone(prev)
            self.assertEqual(nxt, labels[1])
        elif 28 == 32:
            self.assertEqual(prev, labels[31])
            self.assertIsNone(nxt)
        else:
            self.assertEqual(prev, labels[28 - 1])
            self.assertEqual(nxt, labels[28 + 1])
        rebuilt = make_vertebra(lb)
        self.assertEqual(rebuilt.label, lb)
        self.assertIsInstance(is_mobile(lb), bool)

    def test_vertebra_slot_29(self) -> None:
        labels = all_labels()
        lb = labels[29]
        self.assertEqual(ordinal_of(lb), 29)
        col = default_column()
        v = col[29]
        self.assertEqual(v.label, lb)
        self.assertEqual(v.pose.as_tuple(), ZERO_POSE.as_tuple())
        d = dims_for(BY_LABEL[lb])
        self.assertGreater(d.height_mm, 0.0)
        self.assertGreater(d.width_mm, 0.0)
        self.assertGreater(mass_proxy_g(lb), 0.0)
        prev, nxt = neighbor_labels(lb)
        if 29 == 0:
            self.assertIsNone(prev)
            self.assertEqual(nxt, labels[1])
        elif 29 == 32:
            self.assertEqual(prev, labels[31])
            self.assertIsNone(nxt)
        else:
            self.assertEqual(prev, labels[29 - 1])
            self.assertEqual(nxt, labels[29 + 1])
        rebuilt = make_vertebra(lb)
        self.assertEqual(rebuilt.label, lb)
        self.assertIsInstance(is_mobile(lb), bool)

    def test_vertebra_slot_30(self) -> None:
        labels = all_labels()
        lb = labels[30]
        self.assertEqual(ordinal_of(lb), 30)
        col = default_column()
        v = col[30]
        self.assertEqual(v.label, lb)
        self.assertEqual(v.pose.as_tuple(), ZERO_POSE.as_tuple())
        d = dims_for(BY_LABEL[lb])
        self.assertGreater(d.height_mm, 0.0)
        self.assertGreater(d.width_mm, 0.0)
        self.assertGreater(mass_proxy_g(lb), 0.0)
        prev, nxt = neighbor_labels(lb)
        if 30 == 0:
            self.assertIsNone(prev)
            self.assertEqual(nxt, labels[1])
        elif 30 == 32:
            self.assertEqual(prev, labels[31])
            self.assertIsNone(nxt)
        else:
            self.assertEqual(prev, labels[30 - 1])
            self.assertEqual(nxt, labels[30 + 1])
        rebuilt = make_vertebra(lb)
        self.assertEqual(rebuilt.label, lb)
        self.assertIsInstance(is_mobile(lb), bool)

    def test_vertebra_slot_31(self) -> None:
        labels = all_labels()
        lb = labels[31]
        self.assertEqual(ordinal_of(lb), 31)
        col = default_column()
        v = col[31]
        self.assertEqual(v.label, lb)
        self.assertEqual(v.pose.as_tuple(), ZERO_POSE.as_tuple())
        d = dims_for(BY_LABEL[lb])
        self.assertGreater(d.height_mm, 0.0)
        self.assertGreater(d.width_mm, 0.0)
        self.assertGreater(mass_proxy_g(lb), 0.0)
        prev, nxt = neighbor_labels(lb)
        if 31 == 0:
            self.assertIsNone(prev)
            self.assertEqual(nxt, labels[1])
        elif 31 == 32:
            self.assertEqual(prev, labels[31])
            self.assertIsNone(nxt)
        else:
            self.assertEqual(prev, labels[31 - 1])
            self.assertEqual(nxt, labels[31 + 1])
        rebuilt = make_vertebra(lb)
        self.assertEqual(rebuilt.label, lb)
        self.assertIsInstance(is_mobile(lb), bool)

    def test_vertebra_slot_32(self) -> None:
        labels = all_labels()
        lb = labels[32]
        self.assertEqual(ordinal_of(lb), 32)
        col = default_column()
        v = col[32]
        self.assertEqual(v.label, lb)
        self.assertEqual(v.pose.as_tuple(), ZERO_POSE.as_tuple())
        d = dims_for(BY_LABEL[lb])
        self.assertGreater(d.height_mm, 0.0)
        self.assertGreater(d.width_mm, 0.0)
        self.assertGreater(mass_proxy_g(lb), 0.0)
        prev, nxt = neighbor_labels(lb)
        if 32 == 0:
            self.assertIsNone(prev)
            self.assertEqual(nxt, labels[1])
        elif 32 == 32:
            self.assertEqual(prev, labels[31])
            self.assertIsNone(nxt)
        else:
            self.assertEqual(prev, labels[32 - 1])
            self.assertEqual(nxt, labels[32 + 1])
        rebuilt = make_vertebra(lb)
        self.assertEqual(rebuilt.label, lb)
        self.assertIsInstance(is_mobile(lb), bool)

    def test_column_and_dims_catalog_align(self) -> None:
        col = default_column()
        self.assertEqual(len(col), VERTEBRA_N)
        self.assertEqual(len(all_dims()), VERTEBRA_N)
        self.assertEqual(len(DIM_CATALOG), VERTEBRA_N)
        self.assertEqual(set(all_dims()), set(all_labels()))
        self.assertGreater(total_column_height_mm(), 500.0)
        for region in Region:
            self.assertGreater(region_height_mm(region), 0.0)
            filtered = filter_region(col, region)
            self.assertEqual(len(filtered), len(labels_in_region(region)))

    def test_mobile_subset_and_energy(self) -> None:
        col = default_column()
        mobile = mobile_subset(col)
        self.assertLessEqual(len(mobile), len(col))
        self.assertEqual(pose_energy(col), 0.0)
        mapped = by_label(col)
        self.assertEqual(len(mapped), VERTEBRA_N)


class TestPerSegmentExhaustive(unittest.TestCase):

    def test_segment_slot_00(self) -> None:
        col = default_column()
        segs = build_segments(col)
        self.assertEqual(len(segs), SEGMENT_N)
        seg = segs[0]
        self.assertEqual(seg.sid.index, 0)
        self.assertEqual(seg.sid.cranial, col[0].label)
        self.assertEqual(seg.sid.caudal, col[0 + 1].label)
        self.assertEqual(
            segment_index_of(seg.sid.cranial, seg.sid.caudal, segs), 0
        )
        self.assertEqual(segment_by_label(segs)[seg.label].label, seg.label)
        self.assertEqual(len(seg.relative.as_tuple()), 6)
        self.assertGreater(seg.disc.height_mm, 0.0)

    def test_segment_slot_01(self) -> None:
        col = default_column()
        segs = build_segments(col)
        self.assertEqual(len(segs), SEGMENT_N)
        seg = segs[1]
        self.assertEqual(seg.sid.index, 1)
        self.assertEqual(seg.sid.cranial, col[1].label)
        self.assertEqual(seg.sid.caudal, col[1 + 1].label)
        self.assertEqual(
            segment_index_of(seg.sid.cranial, seg.sid.caudal, segs), 1
        )
        self.assertEqual(segment_by_label(segs)[seg.label].label, seg.label)
        self.assertEqual(len(seg.relative.as_tuple()), 6)
        self.assertGreater(seg.disc.height_mm, 0.0)

    def test_segment_slot_02(self) -> None:
        col = default_column()
        segs = build_segments(col)
        self.assertEqual(len(segs), SEGMENT_N)
        seg = segs[2]
        self.assertEqual(seg.sid.index, 2)
        self.assertEqual(seg.sid.cranial, col[2].label)
        self.assertEqual(seg.sid.caudal, col[2 + 1].label)
        self.assertEqual(
            segment_index_of(seg.sid.cranial, seg.sid.caudal, segs), 2
        )
        self.assertEqual(segment_by_label(segs)[seg.label].label, seg.label)
        self.assertEqual(len(seg.relative.as_tuple()), 6)
        self.assertGreater(seg.disc.height_mm, 0.0)

    def test_segment_slot_03(self) -> None:
        col = default_column()
        segs = build_segments(col)
        self.assertEqual(len(segs), SEGMENT_N)
        seg = segs[3]
        self.assertEqual(seg.sid.index, 3)
        self.assertEqual(seg.sid.cranial, col[3].label)
        self.assertEqual(seg.sid.caudal, col[3 + 1].label)
        self.assertEqual(
            segment_index_of(seg.sid.cranial, seg.sid.caudal, segs), 3
        )
        self.assertEqual(segment_by_label(segs)[seg.label].label, seg.label)
        self.assertEqual(len(seg.relative.as_tuple()), 6)
        self.assertGreater(seg.disc.height_mm, 0.0)

    def test_segment_slot_04(self) -> None:
        col = default_column()
        segs = build_segments(col)
        self.assertEqual(len(segs), SEGMENT_N)
        seg = segs[4]
        self.assertEqual(seg.sid.index, 4)
        self.assertEqual(seg.sid.cranial, col[4].label)
        self.assertEqual(seg.sid.caudal, col[4 + 1].label)
        self.assertEqual(
            segment_index_of(seg.sid.cranial, seg.sid.caudal, segs), 4
        )
        self.assertEqual(segment_by_label(segs)[seg.label].label, seg.label)
        self.assertEqual(len(seg.relative.as_tuple()), 6)
        self.assertGreater(seg.disc.height_mm, 0.0)

    def test_segment_slot_05(self) -> None:
        col = default_column()
        segs = build_segments(col)
        self.assertEqual(len(segs), SEGMENT_N)
        seg = segs[5]
        self.assertEqual(seg.sid.index, 5)
        self.assertEqual(seg.sid.cranial, col[5].label)
        self.assertEqual(seg.sid.caudal, col[5 + 1].label)
        self.assertEqual(
            segment_index_of(seg.sid.cranial, seg.sid.caudal, segs), 5
        )
        self.assertEqual(segment_by_label(segs)[seg.label].label, seg.label)
        self.assertEqual(len(seg.relative.as_tuple()), 6)
        self.assertGreater(seg.disc.height_mm, 0.0)

    def test_segment_slot_06(self) -> None:
        col = default_column()
        segs = build_segments(col)
        self.assertEqual(len(segs), SEGMENT_N)
        seg = segs[6]
        self.assertEqual(seg.sid.index, 6)
        self.assertEqual(seg.sid.cranial, col[6].label)
        self.assertEqual(seg.sid.caudal, col[6 + 1].label)
        self.assertEqual(
            segment_index_of(seg.sid.cranial, seg.sid.caudal, segs), 6
        )
        self.assertEqual(segment_by_label(segs)[seg.label].label, seg.label)
        self.assertEqual(len(seg.relative.as_tuple()), 6)
        self.assertGreater(seg.disc.height_mm, 0.0)

    def test_segment_slot_07(self) -> None:
        col = default_column()
        segs = build_segments(col)
        self.assertEqual(len(segs), SEGMENT_N)
        seg = segs[7]
        self.assertEqual(seg.sid.index, 7)
        self.assertEqual(seg.sid.cranial, col[7].label)
        self.assertEqual(seg.sid.caudal, col[7 + 1].label)
        self.assertEqual(
            segment_index_of(seg.sid.cranial, seg.sid.caudal, segs), 7
        )
        self.assertEqual(segment_by_label(segs)[seg.label].label, seg.label)
        self.assertEqual(len(seg.relative.as_tuple()), 6)
        self.assertGreater(seg.disc.height_mm, 0.0)

    def test_segment_slot_08(self) -> None:
        col = default_column()
        segs = build_segments(col)
        self.assertEqual(len(segs), SEGMENT_N)
        seg = segs[8]
        self.assertEqual(seg.sid.index, 8)
        self.assertEqual(seg.sid.cranial, col[8].label)
        self.assertEqual(seg.sid.caudal, col[8 + 1].label)
        self.assertEqual(
            segment_index_of(seg.sid.cranial, seg.sid.caudal, segs), 8
        )
        self.assertEqual(segment_by_label(segs)[seg.label].label, seg.label)
        self.assertEqual(len(seg.relative.as_tuple()), 6)
        self.assertGreater(seg.disc.height_mm, 0.0)

    def test_segment_slot_09(self) -> None:
        col = default_column()
        segs = build_segments(col)
        self.assertEqual(len(segs), SEGMENT_N)
        seg = segs[9]
        self.assertEqual(seg.sid.index, 9)
        self.assertEqual(seg.sid.cranial, col[9].label)
        self.assertEqual(seg.sid.caudal, col[9 + 1].label)
        self.assertEqual(
            segment_index_of(seg.sid.cranial, seg.sid.caudal, segs), 9
        )
        self.assertEqual(segment_by_label(segs)[seg.label].label, seg.label)
        self.assertEqual(len(seg.relative.as_tuple()), 6)
        self.assertGreater(seg.disc.height_mm, 0.0)

    def test_segment_slot_10(self) -> None:
        col = default_column()
        segs = build_segments(col)
        self.assertEqual(len(segs), SEGMENT_N)
        seg = segs[10]
        self.assertEqual(seg.sid.index, 10)
        self.assertEqual(seg.sid.cranial, col[10].label)
        self.assertEqual(seg.sid.caudal, col[10 + 1].label)
        self.assertEqual(
            segment_index_of(seg.sid.cranial, seg.sid.caudal, segs), 10
        )
        self.assertEqual(segment_by_label(segs)[seg.label].label, seg.label)
        self.assertEqual(len(seg.relative.as_tuple()), 6)
        self.assertGreater(seg.disc.height_mm, 0.0)

    def test_segment_slot_11(self) -> None:
        col = default_column()
        segs = build_segments(col)
        self.assertEqual(len(segs), SEGMENT_N)
        seg = segs[11]
        self.assertEqual(seg.sid.index, 11)
        self.assertEqual(seg.sid.cranial, col[11].label)
        self.assertEqual(seg.sid.caudal, col[11 + 1].label)
        self.assertEqual(
            segment_index_of(seg.sid.cranial, seg.sid.caudal, segs), 11
        )
        self.assertEqual(segment_by_label(segs)[seg.label].label, seg.label)
        self.assertEqual(len(seg.relative.as_tuple()), 6)
        self.assertGreater(seg.disc.height_mm, 0.0)

    def test_segment_slot_12(self) -> None:
        col = default_column()
        segs = build_segments(col)
        self.assertEqual(len(segs), SEGMENT_N)
        seg = segs[12]
        self.assertEqual(seg.sid.index, 12)
        self.assertEqual(seg.sid.cranial, col[12].label)
        self.assertEqual(seg.sid.caudal, col[12 + 1].label)
        self.assertEqual(
            segment_index_of(seg.sid.cranial, seg.sid.caudal, segs), 12
        )
        self.assertEqual(segment_by_label(segs)[seg.label].label, seg.label)
        self.assertEqual(len(seg.relative.as_tuple()), 6)
        self.assertGreater(seg.disc.height_mm, 0.0)

    def test_segment_slot_13(self) -> None:
        col = default_column()
        segs = build_segments(col)
        self.assertEqual(len(segs), SEGMENT_N)
        seg = segs[13]
        self.assertEqual(seg.sid.index, 13)
        self.assertEqual(seg.sid.cranial, col[13].label)
        self.assertEqual(seg.sid.caudal, col[13 + 1].label)
        self.assertEqual(
            segment_index_of(seg.sid.cranial, seg.sid.caudal, segs), 13
        )
        self.assertEqual(segment_by_label(segs)[seg.label].label, seg.label)
        self.assertEqual(len(seg.relative.as_tuple()), 6)
        self.assertGreater(seg.disc.height_mm, 0.0)

    def test_segment_slot_14(self) -> None:
        col = default_column()
        segs = build_segments(col)
        self.assertEqual(len(segs), SEGMENT_N)
        seg = segs[14]
        self.assertEqual(seg.sid.index, 14)
        self.assertEqual(seg.sid.cranial, col[14].label)
        self.assertEqual(seg.sid.caudal, col[14 + 1].label)
        self.assertEqual(
            segment_index_of(seg.sid.cranial, seg.sid.caudal, segs), 14
        )
        self.assertEqual(segment_by_label(segs)[seg.label].label, seg.label)
        self.assertEqual(len(seg.relative.as_tuple()), 6)
        self.assertGreater(seg.disc.height_mm, 0.0)

    def test_segment_slot_15(self) -> None:
        col = default_column()
        segs = build_segments(col)
        self.assertEqual(len(segs), SEGMENT_N)
        seg = segs[15]
        self.assertEqual(seg.sid.index, 15)
        self.assertEqual(seg.sid.cranial, col[15].label)
        self.assertEqual(seg.sid.caudal, col[15 + 1].label)
        self.assertEqual(
            segment_index_of(seg.sid.cranial, seg.sid.caudal, segs), 15
        )
        self.assertEqual(segment_by_label(segs)[seg.label].label, seg.label)
        self.assertEqual(len(seg.relative.as_tuple()), 6)
        self.assertGreater(seg.disc.height_mm, 0.0)

    def test_segment_slot_16(self) -> None:
        col = default_column()
        segs = build_segments(col)
        self.assertEqual(len(segs), SEGMENT_N)
        seg = segs[16]
        self.assertEqual(seg.sid.index, 16)
        self.assertEqual(seg.sid.cranial, col[16].label)
        self.assertEqual(seg.sid.caudal, col[16 + 1].label)
        self.assertEqual(
            segment_index_of(seg.sid.cranial, seg.sid.caudal, segs), 16
        )
        self.assertEqual(segment_by_label(segs)[seg.label].label, seg.label)
        self.assertEqual(len(seg.relative.as_tuple()), 6)
        self.assertGreater(seg.disc.height_mm, 0.0)

    def test_segment_slot_17(self) -> None:
        col = default_column()
        segs = build_segments(col)
        self.assertEqual(len(segs), SEGMENT_N)
        seg = segs[17]
        self.assertEqual(seg.sid.index, 17)
        self.assertEqual(seg.sid.cranial, col[17].label)
        self.assertEqual(seg.sid.caudal, col[17 + 1].label)
        self.assertEqual(
            segment_index_of(seg.sid.cranial, seg.sid.caudal, segs), 17
        )
        self.assertEqual(segment_by_label(segs)[seg.label].label, seg.label)
        self.assertEqual(len(seg.relative.as_tuple()), 6)
        self.assertGreater(seg.disc.height_mm, 0.0)

    def test_segment_slot_18(self) -> None:
        col = default_column()
        segs = build_segments(col)
        self.assertEqual(len(segs), SEGMENT_N)
        seg = segs[18]
        self.assertEqual(seg.sid.index, 18)
        self.assertEqual(seg.sid.cranial, col[18].label)
        self.assertEqual(seg.sid.caudal, col[18 + 1].label)
        self.assertEqual(
            segment_index_of(seg.sid.cranial, seg.sid.caudal, segs), 18
        )
        self.assertEqual(segment_by_label(segs)[seg.label].label, seg.label)
        self.assertEqual(len(seg.relative.as_tuple()), 6)
        self.assertGreater(seg.disc.height_mm, 0.0)

    def test_segment_slot_19(self) -> None:
        col = default_column()
        segs = build_segments(col)
        self.assertEqual(len(segs), SEGMENT_N)
        seg = segs[19]
        self.assertEqual(seg.sid.index, 19)
        self.assertEqual(seg.sid.cranial, col[19].label)
        self.assertEqual(seg.sid.caudal, col[19 + 1].label)
        self.assertEqual(
            segment_index_of(seg.sid.cranial, seg.sid.caudal, segs), 19
        )
        self.assertEqual(segment_by_label(segs)[seg.label].label, seg.label)
        self.assertEqual(len(seg.relative.as_tuple()), 6)
        self.assertGreater(seg.disc.height_mm, 0.0)

    def test_segment_slot_20(self) -> None:
        col = default_column()
        segs = build_segments(col)
        self.assertEqual(len(segs), SEGMENT_N)
        seg = segs[20]
        self.assertEqual(seg.sid.index, 20)
        self.assertEqual(seg.sid.cranial, col[20].label)
        self.assertEqual(seg.sid.caudal, col[20 + 1].label)
        self.assertEqual(
            segment_index_of(seg.sid.cranial, seg.sid.caudal, segs), 20
        )
        self.assertEqual(segment_by_label(segs)[seg.label].label, seg.label)
        self.assertEqual(len(seg.relative.as_tuple()), 6)
        self.assertGreater(seg.disc.height_mm, 0.0)

    def test_segment_slot_21(self) -> None:
        col = default_column()
        segs = build_segments(col)
        self.assertEqual(len(segs), SEGMENT_N)
        seg = segs[21]
        self.assertEqual(seg.sid.index, 21)
        self.assertEqual(seg.sid.cranial, col[21].label)
        self.assertEqual(seg.sid.caudal, col[21 + 1].label)
        self.assertEqual(
            segment_index_of(seg.sid.cranial, seg.sid.caudal, segs), 21
        )
        self.assertEqual(segment_by_label(segs)[seg.label].label, seg.label)
        self.assertEqual(len(seg.relative.as_tuple()), 6)
        self.assertGreater(seg.disc.height_mm, 0.0)

    def test_segment_slot_22(self) -> None:
        col = default_column()
        segs = build_segments(col)
        self.assertEqual(len(segs), SEGMENT_N)
        seg = segs[22]
        self.assertEqual(seg.sid.index, 22)
        self.assertEqual(seg.sid.cranial, col[22].label)
        self.assertEqual(seg.sid.caudal, col[22 + 1].label)
        self.assertEqual(
            segment_index_of(seg.sid.cranial, seg.sid.caudal, segs), 22
        )
        self.assertEqual(segment_by_label(segs)[seg.label].label, seg.label)
        self.assertEqual(len(seg.relative.as_tuple()), 6)
        self.assertGreater(seg.disc.height_mm, 0.0)

    def test_segment_slot_23(self) -> None:
        col = default_column()
        segs = build_segments(col)
        self.assertEqual(len(segs), SEGMENT_N)
        seg = segs[23]
        self.assertEqual(seg.sid.index, 23)
        self.assertEqual(seg.sid.cranial, col[23].label)
        self.assertEqual(seg.sid.caudal, col[23 + 1].label)
        self.assertEqual(
            segment_index_of(seg.sid.cranial, seg.sid.caudal, segs), 23
        )
        self.assertEqual(segment_by_label(segs)[seg.label].label, seg.label)
        self.assertEqual(len(seg.relative.as_tuple()), 6)
        self.assertGreater(seg.disc.height_mm, 0.0)

    def test_segment_slot_24(self) -> None:
        col = default_column()
        segs = build_segments(col)
        self.assertEqual(len(segs), SEGMENT_N)
        seg = segs[24]
        self.assertEqual(seg.sid.index, 24)
        self.assertEqual(seg.sid.cranial, col[24].label)
        self.assertEqual(seg.sid.caudal, col[24 + 1].label)
        self.assertEqual(
            segment_index_of(seg.sid.cranial, seg.sid.caudal, segs), 24
        )
        self.assertEqual(segment_by_label(segs)[seg.label].label, seg.label)
        self.assertEqual(len(seg.relative.as_tuple()), 6)
        self.assertGreater(seg.disc.height_mm, 0.0)

    def test_segment_slot_25(self) -> None:
        col = default_column()
        segs = build_segments(col)
        self.assertEqual(len(segs), SEGMENT_N)
        seg = segs[25]
        self.assertEqual(seg.sid.index, 25)
        self.assertEqual(seg.sid.cranial, col[25].label)
        self.assertEqual(seg.sid.caudal, col[25 + 1].label)
        self.assertEqual(
            segment_index_of(seg.sid.cranial, seg.sid.caudal, segs), 25
        )
        self.assertEqual(segment_by_label(segs)[seg.label].label, seg.label)
        self.assertEqual(len(seg.relative.as_tuple()), 6)
        self.assertGreater(seg.disc.height_mm, 0.0)

    def test_segment_slot_26(self) -> None:
        col = default_column()
        segs = build_segments(col)
        self.assertEqual(len(segs), SEGMENT_N)
        seg = segs[26]
        self.assertEqual(seg.sid.index, 26)
        self.assertEqual(seg.sid.cranial, col[26].label)
        self.assertEqual(seg.sid.caudal, col[26 + 1].label)
        self.assertEqual(
            segment_index_of(seg.sid.cranial, seg.sid.caudal, segs), 26
        )
        self.assertEqual(segment_by_label(segs)[seg.label].label, seg.label)
        self.assertEqual(len(seg.relative.as_tuple()), 6)
        self.assertGreater(seg.disc.height_mm, 0.0)

    def test_segment_slot_27(self) -> None:
        col = default_column()
        segs = build_segments(col)
        self.assertEqual(len(segs), SEGMENT_N)
        seg = segs[27]
        self.assertEqual(seg.sid.index, 27)
        self.assertEqual(seg.sid.cranial, col[27].label)
        self.assertEqual(seg.sid.caudal, col[27 + 1].label)
        self.assertEqual(
            segment_index_of(seg.sid.cranial, seg.sid.caudal, segs), 27
        )
        self.assertEqual(segment_by_label(segs)[seg.label].label, seg.label)
        self.assertEqual(len(seg.relative.as_tuple()), 6)
        self.assertGreater(seg.disc.height_mm, 0.0)

    def test_segment_slot_28(self) -> None:
        col = default_column()
        segs = build_segments(col)
        self.assertEqual(len(segs), SEGMENT_N)
        seg = segs[28]
        self.assertEqual(seg.sid.index, 28)
        self.assertEqual(seg.sid.cranial, col[28].label)
        self.assertEqual(seg.sid.caudal, col[28 + 1].label)
        self.assertEqual(
            segment_index_of(seg.sid.cranial, seg.sid.caudal, segs), 28
        )
        self.assertEqual(segment_by_label(segs)[seg.label].label, seg.label)
        self.assertEqual(len(seg.relative.as_tuple()), 6)
        self.assertGreater(seg.disc.height_mm, 0.0)

    def test_segment_slot_29(self) -> None:
        col = default_column()
        segs = build_segments(col)
        self.assertEqual(len(segs), SEGMENT_N)
        seg = segs[29]
        self.assertEqual(seg.sid.index, 29)
        self.assertEqual(seg.sid.cranial, col[29].label)
        self.assertEqual(seg.sid.caudal, col[29 + 1].label)
        self.assertEqual(
            segment_index_of(seg.sid.cranial, seg.sid.caudal, segs), 29
        )
        self.assertEqual(segment_by_label(segs)[seg.label].label, seg.label)
        self.assertEqual(len(seg.relative.as_tuple()), 6)
        self.assertGreater(seg.disc.height_mm, 0.0)

    def test_segment_slot_30(self) -> None:
        col = default_column()
        segs = build_segments(col)
        self.assertEqual(len(segs), SEGMENT_N)
        seg = segs[30]
        self.assertEqual(seg.sid.index, 30)
        self.assertEqual(seg.sid.cranial, col[30].label)
        self.assertEqual(seg.sid.caudal, col[30 + 1].label)
        self.assertEqual(
            segment_index_of(seg.sid.cranial, seg.sid.caudal, segs), 30
        )
        self.assertEqual(segment_by_label(segs)[seg.label].label, seg.label)
        self.assertEqual(len(seg.relative.as_tuple()), 6)
        self.assertGreater(seg.disc.height_mm, 0.0)

    def test_segment_slot_31(self) -> None:
        col = default_column()
        segs = build_segments(col)
        self.assertEqual(len(segs), SEGMENT_N)
        seg = segs[31]
        self.assertEqual(seg.sid.index, 31)
        self.assertEqual(seg.sid.cranial, col[31].label)
        self.assertEqual(seg.sid.caudal, col[31 + 1].label)
        self.assertEqual(
            segment_index_of(seg.sid.cranial, seg.sid.caudal, segs), 31
        )
        self.assertEqual(segment_by_label(segs)[seg.label].label, seg.label)
        self.assertEqual(len(seg.relative.as_tuple()), 6)
        self.assertGreater(seg.disc.height_mm, 0.0)

    def test_segment_aggregates(self) -> None:
        col = default_column()
        segs = build_segments(col)
        self.assertGreater(total_disc_height_mm(segs), 0.0)
        self.assertGreater(mean_axial_stiffness(segs), 0.0)
        mobile = mobile_segments(segs)
        self.assertGreater(len(mobile), 0)
        self.assertTrue(all(not s.locked for s in mobile))


if __name__ == "__main__":
    unittest.main()
