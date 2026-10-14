"""SC-160 capability organs. VOL-178. sbom.py not forked."""
from __future__ import annotations

from skeleton.supply_chain.vol178.caps.c001_component_id_grammar import Organ as Organ001
from skeleton.supply_chain.vol178.caps.c002_duplicate_id_reject import Organ as Organ002
from skeleton.supply_chain.vol178.caps.c003_name_token import Organ as Organ003
from skeleton.supply_chain.vol178.caps.c004_version_token import Organ as Organ004
from skeleton.supply_chain.vol178.caps.c005_empty_component_reject import Organ as Organ005
from skeleton.supply_chain.vol178.caps.c006_id_cap import Organ as Organ006
from skeleton.supply_chain.vol178.caps.c007_sorted_id_fold import Organ as Organ007
from skeleton.supply_chain.vol178.caps.c008_identity_epoch import Organ as Organ008
from skeleton.supply_chain.vol178.caps.c009_sha256_bind import Organ as Organ009
from skeleton.supply_chain.vol178.caps.c010_non_hex_reject import Organ as Organ010
from skeleton.supply_chain.vol178.caps.c011_canonical_json import Organ as Organ011
from skeleton.supply_chain.vol178.caps.c012_digest_mismatch import Organ as Organ012
from skeleton.supply_chain.vol178.caps.c013_upper_hex_reject import Organ as Organ013
from skeleton.supply_chain.vol178.caps.c014_short_digest import Organ as Organ014
from skeleton.supply_chain.vol178.caps.c015_fold_order import Organ as Organ015
from skeleton.supply_chain.vol178.caps.c016_digest_epoch import Organ as Organ016
from skeleton.supply_chain.vol178.caps.c017_license_allow import Organ as Organ017
from skeleton.supply_chain.vol178.caps.c018_unknown_license import Organ as Organ018
from skeleton.supply_chain.vol178.caps.c019_spdx_token import Organ as Organ019
from skeleton.supply_chain.vol178.caps.c020_license_empty import Organ as Organ020
from skeleton.supply_chain.vol178.caps.c021_dual_license_split import Organ as Organ021
from skeleton.supply_chain.vol178.caps.c022_license_epoch import Organ as Organ022
from skeleton.supply_chain.vol178.caps.c023_copyleft_flag import Organ as Organ023
from skeleton.supply_chain.vol178.caps.c024_license_cap import Organ as Organ024
from skeleton.supply_chain.vol178.caps.c025_scope_direct import Organ as Organ025
from skeleton.supply_chain.vol178.caps.c026_scope_transitive import Organ as Organ026
from skeleton.supply_chain.vol178.caps.c027_scope_native import Organ as Organ027
from skeleton.supply_chain.vol178.caps.c028_scope_container import Organ as Organ028
from skeleton.supply_chain.vol178.caps.c029_scope_unknown import Organ as Organ029
from skeleton.supply_chain.vol178.caps.c030_scope_coverage import Organ as Organ030
from skeleton.supply_chain.vol178.caps.c031_scope_duplicate import Organ as Organ031
from skeleton.supply_chain.vol178.caps.c032_scope_epoch import Organ as Organ032
from skeleton.supply_chain.vol178.caps.c033_advisory_token import Organ as Organ033
from skeleton.supply_chain.vol178.caps.c034_advisory_bind import Organ as Organ034
from skeleton.supply_chain.vol178.caps.c035_unknown_component import Organ as Organ035
from skeleton.supply_chain.vol178.caps.c036_advisory_dup import Organ as Organ036
from skeleton.supply_chain.vol178.caps.c037_advisory_empty import Organ as Organ037
from skeleton.supply_chain.vol178.caps.c038_advisory_cap import Organ as Organ038
from skeleton.supply_chain.vol178.caps.c039_advisory_fold import Organ as Organ039
from skeleton.supply_chain.vol178.caps.c040_advisory_epoch import Organ as Organ040
from skeleton.supply_chain.vol178.caps.c041_severity_rank import Organ as Organ041
from skeleton.supply_chain.vol178.caps.c042_critical_shunt import Organ as Organ042
from skeleton.supply_chain.vol178.caps.c043_unknown_severity import Organ as Organ043
from skeleton.supply_chain.vol178.caps.c044_severity_order import Organ as Organ044
from skeleton.supply_chain.vol178.caps.c045_high_hold import Organ as Organ045
from skeleton.supply_chain.vol178.caps.c046_medium_pass import Organ as Organ046
from skeleton.supply_chain.vol178.caps.c047_low_pass import Organ as Organ047
from skeleton.supply_chain.vol178.caps.c048_severity_epoch import Organ as Organ048
from skeleton.supply_chain.vol178.caps.c049_status_open import Organ as Organ049
from skeleton.supply_chain.vol178.caps.c050_status_fixed import Organ as Organ050
from skeleton.supply_chain.vol178.caps.c051_status_accepted import Organ as Organ051
from skeleton.supply_chain.vol178.caps.c052_status_not_affected import Organ as Organ052
from skeleton.supply_chain.vol178.caps.c053_status_illegal import Organ as Organ053
from skeleton.supply_chain.vol178.caps.c054_status_rewind import Organ as Organ054
from skeleton.supply_chain.vol178.caps.c055_status_once import Organ as Organ055
from skeleton.supply_chain.vol178.caps.c056_status_epoch import Organ as Organ056
from skeleton.supply_chain.vol178.caps.c057_revision_pin import Organ as Organ057
from skeleton.supply_chain.vol178.caps.c058_revision_len import Organ as Organ058
from skeleton.supply_chain.vol178.caps.c059_revision_case import Organ as Organ059
from skeleton.supply_chain.vol178.caps.c060_revision_mismatch import Organ as Organ060
from skeleton.supply_chain.vol178.caps.c061_revision_empty import Organ as Organ061
from skeleton.supply_chain.vol178.caps.c062_revision_fold import Organ as Organ062
from skeleton.supply_chain.vol178.caps.c063_revision_epoch import Organ as Organ063
from skeleton.supply_chain.vol178.caps.c064_revision_bind import Organ as Organ064
from skeleton.supply_chain.vol178.caps.c065_purl_type import Organ as Organ065
from skeleton.supply_chain.vol178.caps.c066_purl_name import Organ as Organ066
from skeleton.supply_chain.vol178.caps.c067_purl_version import Organ as Organ067
from skeleton.supply_chain.vol178.caps.c068_purl_qual import Organ as Organ068
from skeleton.supply_chain.vol178.caps.c069_purl_empty import Organ as Organ069
from skeleton.supply_chain.vol178.caps.c070_purl_space import Organ as Organ070
from skeleton.supply_chain.vol178.caps.c071_purl_cap import Organ as Organ071
from skeleton.supply_chain.vol178.caps.c072_purl_epoch import Organ as Organ072
from skeleton.supply_chain.vol178.caps.c073_closure_bound import Organ as Organ073
from skeleton.supply_chain.vol178.caps.c074_closure_cycle import Organ as Organ074
from skeleton.supply_chain.vol178.caps.c075_closure_depth import Organ as Organ075
from skeleton.supply_chain.vol178.caps.c076_closure_orphan import Organ as Organ076
from skeleton.supply_chain.vol178.caps.c077_closure_clip import Organ as Organ077
from skeleton.supply_chain.vol178.caps.c078_closure_reverse import Organ as Organ078
from skeleton.supply_chain.vol178.caps.c079_closure_fold import Organ as Organ079
from skeleton.supply_chain.vol178.caps.c080_closure_epoch import Organ as Organ080
from skeleton.supply_chain.vol178.caps.c081_native_abi import Organ as Organ081
from skeleton.supply_chain.vol178.caps.c082_native_triple import Organ as Organ082
from skeleton.supply_chain.vol178.caps.c083_native_missing import Organ as Organ083
from skeleton.supply_chain.vol178.caps.c084_native_dup import Organ as Organ084
from skeleton.supply_chain.vol178.caps.c085_native_cap import Organ as Organ085
from skeleton.supply_chain.vol178.caps.c086_native_fold import Organ as Organ086
from skeleton.supply_chain.vol178.caps.c087_native_epoch import Organ as Organ087
from skeleton.supply_chain.vol178.caps.c088_native_pin import Organ as Organ088
from skeleton.supply_chain.vol178.caps.c089_image_digest import Organ as Organ089
from skeleton.supply_chain.vol178.caps.c090_image_tag_reject import Organ as Organ090
from skeleton.supply_chain.vol178.caps.c091_image_registry import Organ as Organ091
from skeleton.supply_chain.vol178.caps.c092_image_dup import Organ as Organ092
from skeleton.supply_chain.vol178.caps.c093_image_cap import Organ as Organ093
from skeleton.supply_chain.vol178.caps.c094_image_fold import Organ as Organ094
from skeleton.supply_chain.vol178.caps.c095_image_epoch import Organ as Organ095
from skeleton.supply_chain.vol178.caps.c096_image_pin import Organ as Organ096
from skeleton.supply_chain.vol178.caps.c097_witness_root import Organ as Organ097
from skeleton.supply_chain.vol178.caps.c098_witness_gap import Organ as Organ098
from skeleton.supply_chain.vol178.caps.c099_witness_tamper import Organ as Organ099
from skeleton.supply_chain.vol178.caps.c100_witness_quorum import Organ as Organ100
from skeleton.supply_chain.vol178.caps.c101_witness_history import Organ as Organ101
from skeleton.supply_chain.vol178.caps.c102_witness_fold import Organ as Organ102
from skeleton.supply_chain.vol178.caps.c103_witness_epoch import Organ as Organ103
from skeleton.supply_chain.vol178.caps.c104_witness_seal import Organ as Organ104
from skeleton.supply_chain.vol178.caps.c105_replay_root import Organ as Organ105
from skeleton.supply_chain.vol178.caps.c106_replay_pop import Organ as Organ106
from skeleton.supply_chain.vol178.caps.c107_replay_gap import Organ as Organ107
from skeleton.supply_chain.vol178.caps.c108_replay_order import Organ as Organ108
from skeleton.supply_chain.vol178.caps.c109_replay_empty import Organ as Organ109
from skeleton.supply_chain.vol178.caps.c110_replay_clip import Organ as Organ110
from skeleton.supply_chain.vol178.caps.c111_replay_fold import Organ as Organ111
from skeleton.supply_chain.vol178.caps.c112_replay_epoch import Organ as Organ112
from skeleton.supply_chain.vol178.caps.c113_risk_cap import Organ as Organ113
from skeleton.supply_chain.vol178.caps.c114_risk_reason_ptr import Organ as Organ114
from skeleton.supply_chain.vol178.caps.c115_risk_expired import Organ as Organ115
from skeleton.supply_chain.vol178.caps.c116_risk_dup import Organ as Organ116
from skeleton.supply_chain.vol178.caps.c117_risk_critical_block import Organ as Organ117
from skeleton.supply_chain.vol178.caps.c118_risk_fold import Organ as Organ118
from skeleton.supply_chain.vol178.caps.c119_risk_epoch import Organ as Organ119
from skeleton.supply_chain.vol178.caps.c120_risk_reverse import Organ as Organ120
from skeleton.supply_chain.vol178.caps.c121_observe_card import Organ as Organ121
from skeleton.supply_chain.vol178.caps.c122_capability_index import Organ as Organ122
from skeleton.supply_chain.vol178.caps.c123_failure_rollup import Organ as Organ123
from skeleton.supply_chain.vol178.caps.c124_security_card import Organ as Organ124
from skeleton.supply_chain.vol178.caps.c125_mass_clip import Organ as Organ125
from skeleton.supply_chain.vol178.caps.c126_stored_prose_gate import Organ as Organ126
from skeleton.supply_chain.vol178.caps.c127_parent_cite import Organ as Organ127
from skeleton.supply_chain.vol178.caps.c128_batch_snapshot import Organ as Organ128
from skeleton.supply_chain.vol178.caps.c129_sbom_format_lock import Organ as Organ129
from skeleton.supply_chain.vol178.caps.c130_generated_by_token import Organ as Organ130
from skeleton.supply_chain.vol178.caps.c131_finding_bind import Organ as Organ131
from skeleton.supply_chain.vol178.caps.c132_component_sort import Organ as Organ132
from skeleton.supply_chain.vol178.caps.c133_heat_shunt import Organ as Organ133
from skeleton.supply_chain.vol178.caps.c134_cool_path import Organ as Organ134
from skeleton.supply_chain.vol178.caps.c135_bag_reverse import Organ as Organ135
from skeleton.supply_chain.vol178.caps.c136_count_lock import Organ as Organ136
from skeleton.supply_chain.vol178.caps.c137_license_ref_ptr import Organ as Organ137
from skeleton.supply_chain.vol178.caps.c138_scope_gap_card import Organ as Organ138
from skeleton.supply_chain.vol178.caps.c139_advisory_hold import Organ as Organ139
from skeleton.supply_chain.vol178.caps.c140_severity_floor import Organ as Organ140
from skeleton.supply_chain.vol178.caps.c141_status_terminal import Organ as Organ141
from skeleton.supply_chain.vol178.caps.c142_revision_prefix import Organ as Organ142
from skeleton.supply_chain.vol178.caps.c143_purl_namespace import Organ as Organ143
from skeleton.supply_chain.vol178.caps.c144_closure_width import Organ as Organ144
from skeleton.supply_chain.vol178.caps.c145_native_soname import Organ as Organ145
from skeleton.supply_chain.vol178.caps.c146_image_platform import Organ as Organ146
from skeleton.supply_chain.vol178.caps.c147_witness_leaf import Organ as Organ147
from skeleton.supply_chain.vol178.caps.c148_replay_width import Organ as Organ148
from skeleton.supply_chain.vol178.caps.c149_risk_pointer import Organ as Organ149
from skeleton.supply_chain.vol178.caps.c150_export_parent import Organ as Organ150
from skeleton.supply_chain.vol178.caps.c151_format_reject import Organ as Organ151
from skeleton.supply_chain.vol178.caps.c152_canon_order import Organ as Organ152
from skeleton.supply_chain.vol178.caps.c153_direct_pin import Organ as Organ153
from skeleton.supply_chain.vol178.caps.c154_transitive_pin import Organ as Organ154
from skeleton.supply_chain.vol178.caps.c155_native_pin_extra import Organ as Organ155
from skeleton.supply_chain.vol178.caps.c156_container_pin_extra import Organ as Organ156
from skeleton.supply_chain.vol178.caps.c157_open_hold import Organ as Organ157
from skeleton.supply_chain.vol178.caps.c158_fixed_fold import Organ as Organ158
from skeleton.supply_chain.vol178.caps.c159_sha_fold import Organ as Organ159
from skeleton.supply_chain.vol178.caps.c160_id_fold import Organ as Organ160

ORGANS = [
    ("SC160-001", "component_id_grammar", Organ001),
    ("SC160-002", "duplicate_id_reject", Organ002),
    ("SC160-003", "name_token", Organ003),
    ("SC160-004", "version_token", Organ004),
    ("SC160-005", "empty_component_reject", Organ005),
    ("SC160-006", "id_cap", Organ006),
    ("SC160-007", "sorted_id_fold", Organ007),
    ("SC160-008", "identity_epoch", Organ008),
    ("SC160-009", "sha256_bind", Organ009),
    ("SC160-010", "non_hex_reject", Organ010),
    ("SC160-011", "canonical_json", Organ011),
    ("SC160-012", "digest_mismatch", Organ012),
    ("SC160-013", "upper_hex_reject", Organ013),
    ("SC160-014", "short_digest", Organ014),
    ("SC160-015", "fold_order", Organ015),
    ("SC160-016", "digest_epoch", Organ016),
    ("SC160-017", "license_allow", Organ017),
    ("SC160-018", "unknown_license", Organ018),
    ("SC160-019", "spdx_token", Organ019),
    ("SC160-020", "license_empty", Organ020),
    ("SC160-021", "dual_license_split", Organ021),
    ("SC160-022", "license_epoch", Organ022),
    ("SC160-023", "copyleft_flag", Organ023),
    ("SC160-024", "license_cap", Organ024),
    ("SC160-025", "scope_direct", Organ025),
    ("SC160-026", "scope_transitive", Organ026),
    ("SC160-027", "scope_native", Organ027),
    ("SC160-028", "scope_container", Organ028),
    ("SC160-029", "scope_unknown", Organ029),
    ("SC160-030", "scope_coverage", Organ030),
    ("SC160-031", "scope_duplicate", Organ031),
    ("SC160-032", "scope_epoch", Organ032),
    ("SC160-033", "advisory_token", Organ033),
    ("SC160-034", "advisory_bind", Organ034),
    ("SC160-035", "unknown_component", Organ035),
    ("SC160-036", "advisory_dup", Organ036),
    ("SC160-037", "advisory_empty", Organ037),
    ("SC160-038", "advisory_cap", Organ038),
    ("SC160-039", "advisory_fold", Organ039),
    ("SC160-040", "advisory_epoch", Organ040),
    ("SC160-041", "severity_rank", Organ041),
    ("SC160-042", "critical_shunt", Organ042),
    ("SC160-043", "unknown_severity", Organ043),
    ("SC160-044", "severity_order", Organ044),
    ("SC160-045", "high_hold", Organ045),
    ("SC160-046", "medium_pass", Organ046),
    ("SC160-047", "low_pass", Organ047),
    ("SC160-048", "severity_epoch", Organ048),
    ("SC160-049", "status_open", Organ049),
    ("SC160-050", "status_fixed", Organ050),
    ("SC160-051", "status_accepted", Organ051),
    ("SC160-052", "status_not_affected", Organ052),
    ("SC160-053", "status_illegal", Organ053),
    ("SC160-054", "status_rewind", Organ054),
    ("SC160-055", "status_once", Organ055),
    ("SC160-056", "status_epoch", Organ056),
    ("SC160-057", "revision_pin", Organ057),
    ("SC160-058", "revision_len", Organ058),
    ("SC160-059", "revision_case", Organ059),
    ("SC160-060", "revision_mismatch", Organ060),
    ("SC160-061", "revision_empty", Organ061),
    ("SC160-062", "revision_fold", Organ062),
    ("SC160-063", "revision_epoch", Organ063),
    ("SC160-064", "revision_bind", Organ064),
    ("SC160-065", "purl_type", Organ065),
    ("SC160-066", "purl_name", Organ066),
    ("SC160-067", "purl_version", Organ067),
    ("SC160-068", "purl_qual", Organ068),
    ("SC160-069", "purl_empty", Organ069),
    ("SC160-070", "purl_space", Organ070),
    ("SC160-071", "purl_cap", Organ071),
    ("SC160-072", "purl_epoch", Organ072),
    ("SC160-073", "closure_bound", Organ073),
    ("SC160-074", "closure_cycle", Organ074),
    ("SC160-075", "closure_depth", Organ075),
    ("SC160-076", "closure_orphan", Organ076),
    ("SC160-077", "closure_clip", Organ077),
    ("SC160-078", "closure_reverse", Organ078),
    ("SC160-079", "closure_fold", Organ079),
    ("SC160-080", "closure_epoch", Organ080),
    ("SC160-081", "native_abi", Organ081),
    ("SC160-082", "native_triple", Organ082),
    ("SC160-083", "native_missing", Organ083),
    ("SC160-084", "native_dup", Organ084),
    ("SC160-085", "native_cap", Organ085),
    ("SC160-086", "native_fold", Organ086),
    ("SC160-087", "native_epoch", Organ087),
    ("SC160-088", "native_pin", Organ088),
    ("SC160-089", "image_digest", Organ089),
    ("SC160-090", "image_tag_reject", Organ090),
    ("SC160-091", "image_registry", Organ091),
    ("SC160-092", "image_dup", Organ092),
    ("SC160-093", "image_cap", Organ093),
    ("SC160-094", "image_fold", Organ094),
    ("SC160-095", "image_epoch", Organ095),
    ("SC160-096", "image_pin", Organ096),
    ("SC160-097", "witness_root", Organ097),
    ("SC160-098", "witness_gap", Organ098),
    ("SC160-099", "witness_tamper", Organ099),
    ("SC160-100", "witness_quorum", Organ100),
    ("SC160-101", "witness_history", Organ101),
    ("SC160-102", "witness_fold", Organ102),
    ("SC160-103", "witness_epoch", Organ103),
    ("SC160-104", "witness_seal", Organ104),
    ("SC160-105", "replay_root", Organ105),
    ("SC160-106", "replay_pop", Organ106),
    ("SC160-107", "replay_gap", Organ107),
    ("SC160-108", "replay_order", Organ108),
    ("SC160-109", "replay_empty", Organ109),
    ("SC160-110", "replay_clip", Organ110),
    ("SC160-111", "replay_fold", Organ111),
    ("SC160-112", "replay_epoch", Organ112),
    ("SC160-113", "risk_cap", Organ113),
    ("SC160-114", "risk_reason_ptr", Organ114),
    ("SC160-115", "risk_expired", Organ115),
    ("SC160-116", "risk_dup", Organ116),
    ("SC160-117", "risk_critical_block", Organ117),
    ("SC160-118", "risk_fold", Organ118),
    ("SC160-119", "risk_epoch", Organ119),
    ("SC160-120", "risk_reverse", Organ120),
    ("SC160-121", "observe_card", Organ121),
    ("SC160-122", "capability_index", Organ122),
    ("SC160-123", "failure_rollup", Organ123),
    ("SC160-124", "security_card", Organ124),
    ("SC160-125", "mass_clip", Organ125),
    ("SC160-126", "stored_prose_gate", Organ126),
    ("SC160-127", "parent_cite", Organ127),
    ("SC160-128", "batch_snapshot", Organ128),
    ("SC160-129", "sbom_format_lock", Organ129),
    ("SC160-130", "generated_by_token", Organ130),
    ("SC160-131", "finding_bind", Organ131),
    ("SC160-132", "component_sort", Organ132),
    ("SC160-133", "heat_shunt", Organ133),
    ("SC160-134", "cool_path", Organ134),
    ("SC160-135", "bag_reverse", Organ135),
    ("SC160-136", "count_lock", Organ136),
    ("SC160-137", "license_ref_ptr", Organ137),
    ("SC160-138", "scope_gap_card", Organ138),
    ("SC160-139", "advisory_hold", Organ139),
    ("SC160-140", "severity_floor", Organ140),
    ("SC160-141", "status_terminal", Organ141),
    ("SC160-142", "revision_prefix", Organ142),
    ("SC160-143", "purl_namespace", Organ143),
    ("SC160-144", "closure_width", Organ144),
    ("SC160-145", "native_soname", Organ145),
    ("SC160-146", "image_platform", Organ146),
    ("SC160-147", "witness_leaf", Organ147),
    ("SC160-148", "replay_width", Organ148),
    ("SC160-149", "risk_pointer", Organ149),
    ("SC160-150", "export_parent", Organ150),
    ("SC160-151", "format_reject", Organ151),
    ("SC160-152", "canon_order", Organ152),
    ("SC160-153", "direct_pin", Organ153),
    ("SC160-154", "transitive_pin", Organ154),
    ("SC160-155", "native_pin_extra", Organ155),
    ("SC160-156", "container_pin_extra", Organ156),
    ("SC160-157", "open_hold", Organ157),
    ("SC160-158", "fixed_fold", Organ158),
    ("SC160-159", "sha_fold", Organ159),
    ("SC160-160", "id_fold", Organ160),
]

