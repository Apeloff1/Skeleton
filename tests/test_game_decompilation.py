"""Rights-gated decompilation contracts using only generated homebrew bytes.

No commercial ROM, console core, native binary execution or production LLM.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import struct
import tempfile
import unittest
import wave
import zipfile
from pathlib import Path

from skeleton.jeeves.game_console_assets import png_rgba, TIMImage, encode_tim
from skeleton.jeeves.game_decompilation import (
    GameDecompilationGrant, decompile_authorized_game,
    prepare_reviewed_training_candidate, SCOPE_STRUCTURE, SCOPE_CODE,
    SCOPE_ASSETS, SCOPE_PREVIEWS, SCOPE_QUALITY, SCOPE_SHADOW,
)
from skeleton.jeeves.game_decompilation_assets import decode_tile_region, extract_nes_chr
from skeleton.jeeves.game_decompilation_code import disassemble_nes_nrom, disassemble_gb_sm83
from skeleton.jeeves.game_decompilation_archives import analyze_zip_project
from skeleton.jeeves.game_decompilation_formats import inspect_binary_structure
from skeleton.jeeves.game_decompilation_arm import disassemble_gba_arm_entry
from skeleton.jeeves.game_decompilation import analyze_authorized_native_frames
from skeleton.jeeves.game_decompilation_learning import (
    make_human_labeled_candidate, train_shadow_asset_quality_model,
    infer_shadow_asset_quality,
)
from skeleton.jeeves.game_decompilation_quality import derive_game_quality_brief
from skeleton.jeeves.game_decompilation_evidence import (verify_game_decompilation_report, verify_human_label_against_report)
from skeleton.jeeves.game_learning_ingestion import _GB_LOGO
from skeleton.jeeves.game_decompilation_capabilities import build_game_decompilation_target_matrix


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def synthetic_nrom(*, chr_rom: bool=True, mapper: int=0) -> bytes:
    header=bytearray(16)
    header[:4]=b"NES\x1a"
    header[4]=1
    header[5]=1 if chr_rom else 0
    header[6]=(mapper&15)<<4
    header[7]=mapper&0xF0
    prg=bytearray([0xEA]*16384)
    # 8000: LDA #7 ; STA $0200 ; BNE $8009 ; BRK; NOP; RTS.
    prg[:11]=bytes([0xA9,7,0x8D,0,2,0xD0,2,0,0xEA,0x60,0])
    prg[0x3FFA:0x4000]=struct.pack("<HHH",0x8000,0x8000,0x8000)
    chr_bytes=bytes([0xFF,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0])*512 if chr_rom else b""
    return bytes(header)+bytes(prg)+chr_bytes


def synthetic_gb() -> bytes:
    rom=bytearray([0]*32768)
    rom[0x100:0x104]=bytes([0xC3,0x50,0x01,0])
    rom[0x104:0x134]=_GB_LOGO
    rom[0x134:0x138]=b"SKL!"
    rom[0x147]=0
    rom[0x148]=0
    rom[0x150:0x156]=bytes([0x3E,0x42,0x18,0x01,0,0xC9])
    checksum=0
    for b in rom[0x134:0x14D]:
        checksum=(checksum-b-1)&255
    rom[0x14D]=checksum
    global_sum=(sum(rom)-rom[0x14E]-rom[0x14F])&65535
    rom[0x14E:0x150]=global_sum.to_bytes(2,"big")
    return bytes(rom)


def synthetic_gba() -> bytes:
    rom=bytearray(4096)
    # Verified ARM B to 0x080000C0. Every instruction is original fixture bytes.
    rom[0:4]=(0xEA00002E).to_bytes(4,"little")
    rom[0xAC:0xB0]=b"SKL0"
    rom[0xB0:0xB2]=b"HB"
    rom[0xB2]=0x96
    rom[0xC0:0xC4]=(0xE3A00001).to_bytes(4,"little")
    rom[0xC4:0xC8]=(0xE12FFF1E).to_bytes(4,"little")
    rom[0xBD]=(-sum(rom[0xA0:0xBD])-0x19)&255
    return bytes(rom)


def grant(data: bytes, *, previews: bool=True, shadow: bool=True):
    scopes=[SCOPE_STRUCTURE,SCOPE_CODE,SCOPE_ASSETS,SCOPE_QUALITY]
    if previews:scopes.append(SCOPE_PREVIEWS)
    if shadow:scopes.append(SCOPE_SHADOW)
    return GameDecompilationGrant(
        source_sha256=digest(data),rights_evidence_digest="a"*64,
        principal_ref="homebrew_test_author",
        approved_scopes=tuple(scopes),rights_acknowledged=True,
    )


class RealStructureAndAssetContracts(unittest.TestCase):
    def test_nes_disassembly_uses_real_vectors_and_reachable_offsets(self):
        rom=synthetic_nrom()
        result=disassemble_nes_nrom(rom,limit=80)
        self.assertEqual(result["vectors"]["reset"],0x8000)
        self.assertEqual(result["instructions"][0]["mnemonic"],"LDA")
        self.assertEqual(result["instructions"][0]["instruction_bytes"],"a907")
        self.assertTrue(any(x["to"]==0x8009 for x in result["control_flow_edges"]))
        self.assertFalse(result["complete_original_source_recovered"])
        self.assertLess(result["instructions_emitted"],80)
        self.assertTrue(all(x["file_offset"]>=16 for x in result["instructions"]))

    def test_unknown_mapper_never_disassembled_as_nrom(self):
        with self.assertRaises(ValueError):
            disassemble_nes_nrom(synthetic_nrom(mapper=2))
        data=synthetic_nrom(mapper=2)
        result=decompile_authorized_game(data,"homebrew.nes",grant=grant(data),
                                         authorize=lambda *args:True)
        self.assertFalse(result.report["code_analysis"]["supported"])

    def test_nes_chr_decoded_tiles_and_exact_preview(self):
        rom=synthetic_nrom()
        analysis,images=extract_nes_chr(rom,preview_authorized=True)
        self.assertEqual(analysis["chr_bank_count"],1)
        self.assertEqual(analysis["total_tiles"],512)
        self.assertEqual(len(images),1)
        self.assertTrue(images[0][1].startswith(b"\x89PNG\r\n\x1a\n"))
        stats=analysis["regions"][0]["statistics"]
        self.assertEqual(stats["exact_duplicate_tile_count"],511)
        self.assertEqual(stats["unique_tile_sha256"],1)
        self.assertEqual(stats["palette_index_pixel_counts"][0]["index"],0)

    def test_nes_chr_ram_is_not_inferred_or_faked(self):
        analysis,images=extract_nes_chr(synthetic_nrom(chr_rom=False),preview_authorized=True)
        self.assertFalse(analysis["chr_present"])
        self.assertEqual(images,())
        self.assertTrue(analysis["chr_ram_cannot_be_recovered_from_static_rom"])

    def test_gb_static_disassembly_has_correct_fixed_bank_targets(self):
        rom=synthetic_gb()
        code=disassemble_gb_sm83(rom,limit=40)
        self.assertEqual(code["entry_address"],0x100)
        self.assertTrue(any(edge["to"]==0x150 for edge in code["control_flow_edges"]))
        self.assertTrue(any(i["instruction_bytes"]=="3e42" for i in code["instructions"]))
        self.assertFalse(code["bank_switched_code_decompiled"])

    def test_gba_arm_entry_has_real_branch_and_no_false_thumb_coverage(self):
        rom=synthetic_gba()
        code=disassemble_gba_arm_entry(rom,limit=20)
        self.assertTrue(code["header_checksum_verified"])
        self.assertTrue(any(edge["to"]==0x080000C0 for edge in code["control_flow_edges"]))
        self.assertTrue(any(row["mnemonic_family"]=="MOV" for row in code["instructions"]))
        self.assertFalse(code["thumb_state_disassembled"])
        self.assertLess(code["instructions_emitted"],20)
        result=decompile_authorized_game(
            rom,"author.gba",grant=grant(rom),authorize=lambda *_:True,
        )
        self.assertTrue(result.report["code_analysis"]["supported"])

    def test_cannot_guess_or_overread_candidate_tile_region(self):
        data=synthetic_gb()
        with self.assertRaises(ValueError):
            decode_tile_region(data,offset=len(data)-2,length=16,
                               codec="gb_2bpp",provenance="operator_declared_candidate")
        with self.assertRaises(ValueError):
            decode_tile_region(data,offset=0,length=15,
                               codec="gb_2bpp",provenance="operator_declared_candidate")
        report,png=decode_tile_region(data,offset=0x200,length=256,
                            codec="gb_2bpp",provenance="operator_declared_candidate")
        self.assertIsNone(png)
        self.assertIn("candidate_not_verified",report["layout_status"])
        self.assertEqual(report["statistics"]["tiles"],16)

    def test_cross_core_binary_formats_not_misrepresented_as_decompiled_source(self):
        payload=bytearray(512)
        payload[:2]=b"MZ"
        struct.pack_into("<I",payload,0x3C,0x80)
        payload[0x80:0x84]=b"PE\0\0"
        struct.pack_into("<HH",payload,0x84,0x14C,1)
        struct.pack_into("<H",payload,0x80+20,0)
        payload[0x98:0xA0]=b".text\0\0\0"
        struct.pack_into("<IIII",payload,0xA0,32,0x1000,8,0x200)
        payload[0x200:0x208]=b"ABCDEFGH"
        result=inspect_binary_structure(bytes(payload),"native.exe")
        self.assertEqual(result["format"],"pe_coff")
        self.assertEqual(result["sections"][0]["raw_sha256"],digest(b"ABCDEFGH"))
        self.assertFalse(result["code_instructions_disassembled"])

    def test_actual_ps1_tim_pixels_and_rights_gated_png(self):
        # Original 2x2 RGB555 red/blue fixture, not Sony or commercial art.
        tim=TIMImage(bits_per_pixel=16,width=2,height=2,
                     pixels=(bytes([0x1F,0,0,0x7C])*2))
        source=encode_tim(tim)
        rights=grant(source)
        report=decompile_authorized_game(
            source,"homebrew.tim",grant=rights,authorize=lambda *_:True,
            export_previews=True,
        )
        self.assertEqual(report.report["format"],"playstation_tim_candidate")
        self.assertEqual(report.report["asset_analysis"]["format"],"ps1_tim_16bpp")
        self.assertEqual(report.report["asset_analysis"]["pixel_count"],4)
        self.assertEqual(len(report.previews),1)
        self.assertTrue(report.previews[0][1].startswith(b"\\x89PNG"))
        silent=decompile_authorized_game(
            source,"homebrew.tim",grant=rights,authorize=lambda *_:True,
            export_previews=False,
        )
        self.assertEqual(silent.previews,())

    def test_image_and_audio_source_metrics_feed_human_review_not_auto_weights(self):
        rgba=bytes([5,10,15,255, 90,100,120,0])*2
        source=png_rgba(rgba,2,2)
        result=decompile_authorized_game(
            source,"original.png",grant=grant(source),authorize=lambda *_:True,
        )
        brief=result.report["quality_brief"]
        self.assertEqual(brief["measured_numeric_features"]["decoded_image_pixels"],4)
        self.assertEqual(brief["measured_numeric_features"]["nonopaque_pixel_fraction"],0.5)
        self.assertFalse(brief["model_training_performed"])
        reviewed=prepare_reviewed_training_candidate(
            result,grant=grant(source),authorize=lambda *_:True,
            human_score=50,reviewer_ref="reviewer",
            label_evidence_digest="b"*64,
        )
        self.assertIn("decoded_image_pixels",reviewed["measured_features"])
        self.assertFalse(reviewed["production_model_or_language_model_updated"])

    def test_existing_png_decodes_actual_rgba_without_export_by_default(self):
        rgba=bytes([60,120,180,255])*4
        source=png_rgba(rgba,2,2)
        report=decompile_authorized_game(
            source,"art.png",grant=grant(source),authorize=lambda *_:True,
        )
        self.assertEqual(report.report["asset_analysis"]["rgba_sha256"],digest(rgba))
        self.assertFalse(report.previews)
        self.assertFalse(report.report["asset_analysis"]["source_media_bytes_exported"])

    def test_nested_zip_not_executed_and_exact_png_assets_measured(self):
        image=png_rgba(bytes([50,100,150,255])*4,2,2)
        container=io.BytesIO()
        with zipfile.ZipFile(container,"w",zipfile.ZIP_DEFLATED) as z:
            z.writestr("sprite.png",image)
            z.writestr("scripts/ai.lua","print('this must not run')")
        result=analyze_zip_project(container.getvalue())
        self.assertEqual(result["member_count"],2)
        self.assertEqual(result["resource_inventory"][0]["resource_kind"],"exact_decoded_png")
        self.assertEqual(result["resource_inventory"][0]["pixels"],4)
        self.assertFalse(result["scripts_executed"])
        self.assertFalse(result["raw_game_assets_exported"])

    def test_zip_pcm_wav_measures_samples_without_exporting_audio(self):
        pcm=io.BytesIO()
        with wave.open(pcm,"wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(bytes([0,0])*256)
        zipped=io.BytesIO()
        with zipfile.ZipFile(zipped,"w",zipfile.ZIP_DEFLATED) as z:
            z.writestr("audio/original_synth.wav",pcm.getvalue())
        report=analyze_zip_project(zipped.getvalue())
        self.assertEqual(report["resource_inventory"][0]["resource_kind"],"measured_pcm_wav")
        self.assertEqual(report["resource_inventory"][0]["sample_rate"],16000)
        self.assertNotIn("pcm",report["resource_inventory"][0])

    def test_zip_traversal_and_case_collisions_are_rejected(self):
        for names in (["../evil.png"],["Pack.png","pack.png"],[".hidden/file"]):
            buffer=io.BytesIO()
            with zipfile.ZipFile(buffer,"w") as z:
                for name in names:z.writestr(name,b"sample")
            with self.subTest(names=names),self.assertRaises(ValueError):
                analyze_zip_project(buffer.getvalue())


class RightsAndEvidenceContracts(unittest.TestCase):
    def test_full_original_rom_is_not_returned_in_report(self):
        rom=synthetic_nrom()
        g=grant(rom)
        scopes=[]
        def approve(action,bound):
            self.assertIs(bound,g)
            scopes.append(action)
            return True
        result=decompile_authorized_game(
            rom,"lawful.nes",grant=g,authorize=approve,export_previews=True,
        )
        self.assertEqual(len(result.previews),1)
        self.assertEqual(len(result.report["preview_artifacts"]),1)
        self.assertEqual(result.report["preview_artifacts"][0]["sha256"],digest(result.previews[0][1]))
        self.assertIn(SCOPE_PREVIEWS,scopes)
        self.assertTrue(result.report["quality_brief"]["raw_game_assets_included"] is False)
        self.assertFalse(result.report["production_model_training_performed"])
        serialized=json.dumps(result.report)
        self.assertNotIn("data_base64",serialized)
        self.assertNotIn("rom_base64",serialized)
        self.assertFalse(result.report["full_original_source_recovered"])

    def test_rights_and_independent_caller_both_required(self):
        rom=synthetic_nrom()
        with self.assertRaises(PermissionError):
            decompile_authorized_game(rom,"lawful.nes",grant=grant(rom),
                                      authorize=lambda *_:False)
        missing=grant(rom,previews=False)
        with self.assertRaises(PermissionError):
            decompile_authorized_game(rom,"lawful.nes",grant=missing,
                                      authorize=lambda *_:True,export_previews=True)
        altered=rom+b"\x00"
        with self.assertRaises(PermissionError):
            decompile_authorized_game(altered,"lawful.nes",
                                      grant=grant(rom),authorize=lambda *_:True)

    def test_original_quality_label_separate_scope_and_hash(self):
        rom=synthetic_nrom()
        result=decompile_authorized_game(
            rom,"lawful.nes",grant=grant(rom),authorize=lambda *_:True,
        )
        g=grant(rom)
        candidate=prepare_reviewed_training_candidate(
            result,grant=g,authorize=lambda *_:True,
            human_score=76,reviewer_ref="test_human",
            label_evidence_digest="b"*64,
        )
        self.assertEqual(candidate["human_quality_score_0_to_100"],76)
        self.assertFalse(candidate["source_assets_embedded"])
        self.assertEqual(candidate["source_sha256"],digest(rom))
        with self.assertRaises(PermissionError):
            prepare_reviewed_training_candidate(
                result,grant=grant(rom,shadow=False),authorize=lambda *_:True,
                human_score=76,reviewer_ref="test_human",
                label_evidence_digest="b"*64,
            )

    def test_quality_brief_and_candidate_cannot_be_modified_undetected(self):
        rom=synthetic_nrom()
        brief=decompile_authorized_game(
            rom,"lawful.nes",grant=grant(rom),authorize=lambda *_:True,
        ).report["quality_brief"]
        modified=copy.deepcopy(brief)
        modified["measured_numeric_features"]["chr_tile_count"]=12345
        with self.assertRaises(ValueError):
            make_human_labeled_candidate(
                modified,score=99,reviewer_ref="reviewer",
                label_evidence_digest="b"*64,training_rights_digest="c"*64,
                authorize=lambda:True,
            )


class RuntimeNativeRGBContracts(unittest.TestCase):
    def test_verified_native_frames_capture_real_spatial_and_temporal_evidence(self):
        original=bytes([0,0,0])*64
        modified=bytes([255,0,0])*64
        source=synthetic_nrom()
        f1={"width":8,"height":8,"pixel_sha256":digest(original),
            "native_run_cursor":12}
        f2={"width":8,"height":8,"pixel_sha256":digest(modified),
            "native_run_cursor":13}
        report=analyze_authorized_native_frames(
            [(f1,original),(f2,modified)],
            grant=grant(source),core_binary_sha256="c"*64,
            authorize=lambda *_:True,
        )
        self.assertEqual(report["frames_measured"],2)
        self.assertAlmostEqual(report["mean_temporal_rgb_change"],1/3,places=6)
        self.assertEqual(report["frame_reports"][1]["delta_native_runs"],1)
        self.assertEqual(report["native_frames_executed_by_this_analyzer"],0)
        self.assertEqual(report["frame_reports"][0]["visual_features"]["tile_columns"],8)
        self.assertFalse(report["production_model_weights_updated"])

    def test_native_rgb_frame_tampering_and_unexecuted_visual_change_rejected(self):
        source=synthetic_nrom()
        rgba=bytes([1,2,3])*64
        bad=bytes([1,2,4])*64
        meta={"width":8,"height":8,"pixel_sha256":digest(rgba),
              "native_run_cursor":17}
        call=lambda rows:analyze_authorized_native_frames(
            rows,grant=grant(source),core_binary_sha256="c"*64,
            authorize=lambda *_:True,
        )
        with self.assertRaises(ValueError):
            call([(meta,bad)])
        with self.assertRaises(ValueError):
            call([(meta,rgba),
                  ({**meta,"pixel_sha256":digest(bad)},bad)])
        with self.assertRaises(ValueError):
            call([(meta,rgba),({**meta,"native_run_cursor":16},rgba)])


class OfflineGameDecompilationEvidenceContracts(unittest.TestCase):
    def test_source_code_assets_and_review_receipts_are_locally_verified(self):
        source=synthetic_nrom()
        report=decompile_authorized_game(
            source,"original.nes",grant=grant(source),
            authorize=lambda *_:True,export_previews=True,
        )
        status=verify_game_decompilation_report(
            report.report,expected_source_sha256=digest(source),
            expected_rights_sha256="a"*64,
        )
        self.assertTrue(status["locally_consistent"])
        self.assertGreater(status["static_instructions_verified_structurally"],0)
        self.assertEqual(status["authorized_preview_receipts"],1)
        self.assertFalse(status["gameplay_fidelity_or_rights_independently_verified"])

    def test_evidence_tampering_with_recomputed_outer_hash_is_still_detected(self):
        from skeleton.jeeves.game_decompilation_quality import _digest
        source=synthetic_nrom()
        data=copy.deepcopy(decompile_authorized_game(
            source,"original.nes",grant=grant(source),
            authorize=lambda *_:True,
        ).report)
        data["code_analysis"]["instructions"][0]["file_offset"]=len(source)+100
        data["report_sha256"]=_digest({k:v for k,v in data.items() if k!="report_sha256"})
        with self.assertRaises(ValueError):
            verify_game_decompilation_report(data)

    def test_human_training_label_bound_to_original_unchanged_review(self):
        source=synthetic_nrom()
        g=grant(source)
        result=decompile_authorized_game(
            source,"original.nes",grant=g,authorize=lambda *_:True,
        )
        label=prepare_reviewed_training_candidate(
            result,grant=g,authorize=lambda *_:True,
            human_score=79,reviewer_ref="reviewer",
            label_evidence_digest="b"*64,
        )
        checked=verify_human_label_against_report(label,result.report)
        self.assertTrue(checked["sources_and_rights_bound"])
        bad=copy.deepcopy(label)
        bad["training_rights_digest"]="c"*64
        with self.assertRaises(ValueError):
            verify_human_label_against_report(bad,result.report)


class ShadowQualityTrainingContracts(unittest.TestCase):
    @staticmethod
    def _sample(n):
        brief=derive_game_quality_brief(
            game_format="test_homebrew",
            source_sha256=digest(str(n).encode()),
            rights_evidence_digest="a"*64,
            asset_analysis={
                "chr_present":True,
                "regions":[{
                    "statistics":{
                        "tiles":100+n*10,
                        "unique_tile_sha256":80+n*5,
                        "exact_duplicate_tile_count":20+n*5,
                        "edge_density_over_possible_neighbors":min(1,n/30),
                    },
                }],
            },
            code_analysis={"instructions_emitted":10+n*2,"control_flow_edges":[]},
        )
        return make_human_labeled_candidate(
            brief,score=30+n*5,reviewer_ref="reviewer",
            label_evidence_digest=digest(b"review-"+bytes([n])),
            training_rights_digest="c"*64,
            authorize=lambda:True,
        )

    def test_real_shadow_gradient_training_and_held_out_receipts(self):
        cases=[self._sample(i) for i in range(12)]
        result=train_shadow_asset_quality_model(cases,authorize=lambda:True,epochs=48)
        self.assertTrue(result["shadow_numeric_parameters_actually_fit"])
        self.assertFalse(result["production_model_weights_updated"])
        self.assertFalse(result["promotion_admissible"])
        self.assertEqual(result["train_cases"]+result["held_out_cases"],12)
        self.assertNotEqual(result["train_source_commitment"],result["validation_source_commitment"])
        repeat=train_shadow_asset_quality_model(cases,authorize=lambda:True,epochs=48)
        self.assertEqual(result["checkpoint_sha256"],repeat["checkpoint_sha256"])
        prediction=infer_shadow_asset_quality(result,cases[0]["measured_features"])
        self.assertGreaterEqual(prediction["relative_human_label_estimate"],0)
        self.assertLessEqual(prediction["relative_human_label_estimate"],100)

    def test_duplicate_or_tampered_shadow_data_rejected(self):
        cases=[self._sample(i) for i in range(10)]
        with self.assertRaises(PermissionError):
            train_shadow_asset_quality_model(cases,authorize=lambda:False)
        with self.assertRaises(ValueError):
            train_shadow_asset_quality_model(cases[:-1]+[cases[0]],authorize=lambda:True)
        bad=copy.deepcopy(cases)
        bad[0]["human_quality_score_0_to_100"]=100
        with self.assertRaises(ValueError):
            train_shadow_asset_quality_model(bad,authorize=lambda:True)


class AllCoreCapabilityGapContracts(unittest.TestCase):
    def test_every_catalogued_console_gets_truthful_code_asset_status(self):
        from skeleton.jeeves.game_emulator_catalog import canonical_targets
        report=build_game_decompilation_target_matrix()
        self.assertEqual(report["summary"]["canonical_targets"],len(canonical_targets()))
        self.assertTrue(report["target_inventory_not_actual_running_emulator_count"])
        self.assertEqual(report["summary"]["production_game_model_weight_promotions_in_this_audit"],0)
        by_id={row["target_id"]:row for row in report["target_rows"]}
        self.assertEqual(by_id["nes"]["static_code_decoder"],"nrom_6502_vectors_only")
        self.assertEqual(by_id["game_boy"]["static_code_decoder"],"sm83_fixed_bank_entry_only")
        self.assertFalse(by_id["snes"]["static_code_supported_subset"])
        self.assertTrue(all(row["native_core_or_game_detected_in_this_audit"] is False
                            for row in report["target_rows"]))


if __name__=="__main__":
    unittest.main()
