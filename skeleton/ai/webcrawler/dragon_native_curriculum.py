"""Evidence-gated native game acquisition curriculum for the Dragon.

The next practice task is selected from concrete platform/source gaps rather
than a random list. Progression requires structural ROM build receipts issued
by a trusted worker, NOT a demo filename, client's XP claim or a static AI
plan. Later SDK families are source practice only until dedicated build tools
and independent emulator checks exist.

No background execution here: decisions are presented to the authenticated
owner, and actual source generation still consumes the existing finite budget.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from collections import Counter
from .dragon_native_targets import CATALOG
from .dragon_native_projects import EMITTERS
from .dragon_native_practice import DragonNativePracticeLab
from .dragon_build_evidence import DragonBuildEvidence
from .dragon_practice_lab import _owner

@dataclass(frozen=True)
class CurriculumMilestone:
    milestone_id:str
    target:str
    genre:str
    requires:tuple[str,...]
    learned_mechanic:str
    weight:int
    group:str

@dataclass(frozen=True)
class CurriculumRecommendation:
    target:str
    genre:str
    milestone_id:str
    reason:str
    priority:int
    previous_attempts:int
    build_evidence_count:int
    proof_level:str="source_requested_not_compiled"

@dataclass(frozen=True)
class CurriculumSnapshot:
    owner:str
    curriculum_level:int
    structural_build_targets:tuple[str,...]
    native_source_attempts:int
    unlocked:tuple[CurriculumRecommendation,...]
    blocked:tuple[dict,...]
    next_recommendation:CurriculumRecommendation|None
    proof_scope:str="structural ROM evidence; gameplay and SDK certification absent"
    schema:str="skeleton.ai.dragon.native_curriculum.v1"

MILESTONES=(
  CurriculumMilestone("gb_input","game_boy","arcade_score_attack",(),
                       "D-pad game logic and SM83 sprites",100,"handheld_8bit"),
  CurriculumMilestone("gb_platforms","game_boy","side_scrolling_platformer",
                       ("game_boy",),"scrolling camera and jump physics",95,"handheld_8bit"),
  CurriculumMilestone("nes_chase","nes","arcade_score_attack",
                       ("game_boy",),"6502 CPU and NES CHR graphics",94,"cartridge_8bit"),
  CurriculumMilestone("nes_scroll","nes","side_scrolling_platformer",
                       ("nes",),"6502 PPU nametable scrolling, A jump and ledge physics",90,"cartridge_8bit"),
  CurriculumMilestone("gbc_palette","game_boy_color","arcade_score_attack",
                       ("game_boy",),"CGB palette RAM and color-only ROM",93,"handheld_8bit"),
  CurriculumMilestone("c64_legacy","commodore_64","arcade_score_attack",
                       ("nes",),"VIC-II, CIA and SID platform input",85,"classic_computer"),
  CurriculumMilestone("sms_palette","master_system","arcade_score_attack",
                       ("nes",),"Z80 VRAM sprites and Sega VDP",83,"cartridge_8bit"),
  CurriculumMilestone("gg_handheld","game_gear","arcade_score_attack",
                       ("game_boy_color",),"handheld VDP and 12-bit CRAM",82,"handheld_8bit"),
  CurriculumMilestone("gba_native","game_boy_advance","arcade_score_attack",
                       ("game_boy_color",),"ARM framebuffer and native 4bpp art",79,"handheld_32bit"),
  CurriculumMilestone("genesis_vdp","genesis","arcade_score_attack",
                       ("nes","game_boy_color"),"68000, SGDK and 4bpp tile packing",72,"cartridge_16bit"),
  CurriculumMilestone("snes_vram","snes","arcade_score_attack",
                       ("nes","game_boy_color"),"65816 BG mode and tile planes",71,"cartridge_16bit"),
  CurriculumMilestone("dos_framebuffer","dos_vga","arcade_score_attack",
                       ("nes",),"native x86 VGA and memory constraints",69,"computer_history"),
  CurriculumMilestone("desktop_action","pc_linux","arcade_score_attack",
                       ("nes","game_boy_color"),"original native SDL engine and controller",65,"desktop"),
  CurriculumMilestone("desktop_platform","pc_linux","side_scrolling_platformer",
                       ("nes","game_boy_color"),"gravity, collisions and multi-stage worlds",64,"desktop"),
  CurriculumMilestone("desktop_rpg","pc_linux","turn_based_rpg",
                       ("nes","game_boy_color"),"mana, inventory and turn state",63,"desktop"),
  CurriculumMilestone("desktop_fps","pc_linux","first_person_shooter",
                       ("nes","game_boy_color"),"DDA software raycast and perspective",62,"desktop_3d"),
  CurriculumMilestone("desktop_rhythm","pc_linux","rhythm_game",
                       ("nes","game_boy_color"),"fixed-frame audio note judgement",61,"desktop_audio"),
  CurriculumMilestone("desktop_logic","pc_linux","fixed_screen_puzzle",
                       ("nes","game_boy_color"),"exact state-space level solving and native C execution",60,"desktop"),
  CurriculumMilestone("n64_joystick","nintendo_64","arcade_score_attack",
                       ("nes","game_boy_color"),"VR4300 libdragon framebuffer and analog pad",59,"console_64bit"),
  CurriculumMilestone("nds_dual","nintendo_ds","arcade_score_attack",
                       ("nes","game_boy_color"),"ARM9 dual screens and resistive touch mechanics",58,"dual_screen_handheld"),
  CurriculumMilestone("psp_analog","psp","arcade_score_attack",
                       ("nes","game_boy_color"),"Allegrex PSPSDK analog controller and LCD",57,"handheld_3d"),
  CurriculumMilestone("ps1_gpu","ps1","arcade_score_attack",
                       ("nes","game_boy_color"),"MIPS PS1 homebrew rendering",54,"console_32bit"),
  CurriculumMilestone("vic20_video","commodore_vic20","arcade_score_attack",
                       ("game_boy",),"Commodore VIC-I memory display and volume",60,"classic_computer"),
  CurriculumMilestone("c128_sid","commodore_128","arcade_score_attack",
                       ("nes",),"8502 VIC-II display and SID audio registers",55,"classic_computer"),
  CurriculumMilestone("atari_8bit","atari_400_800","arcade_score_attack",
                       ("nes",),"ANTIC/GTIA/POKEY controller graphics",54,"classic_computer"),
  CurriculumMilestone("msx1_vdp","msx1","arcade_score_attack",
                       ("nes",),"MSX BIOS/Z80 VDP and keyboard",53,"classic_computer"),
  CurriculumMilestone("cpc_6845","amstrad_cpc","arcade_score_attack",
                       ("nes",),"CPC Z80 firmware and ink palette",52,"classic_computer"),
  CurriculumMilestone("dreamcast_maple","dreamcast","arcade_score_attack",
                       ("nes","game_boy_color"),"SH-4 Maple controller and KOS framebuffer",53,"console_128bit"),
  CurriculumMilestone("ps2_gs","ps2","arcade_score_attack",
                       ("nes","game_boy_color"),"MIPS EE gsKit graphics and SIF controller RPC",52,"console_128bit"),
  CurriculumMilestone("xbox_gamepad","xbox_original","arcade_score_attack",
                       ("nes","game_boy_color"),"nxdk gamepad and GPU SDK source",53,"console_pc_hybrid"),
)
assert all(x.target in EMITTERS and x.target in CATALOG for x in MILESTONES)

class DragonNativeCurriculum:
    def __init__(self,lab:DragonNativePracticeLab,
                 evidence:DragonBuildEvidence|None=None):
        if evidence is not None and evidence.lab is not lab:
            raise ValueError("curriculum evidence must share its native practice ledger")
        self.lab=lab;self.evidence=evidence

    def evaluate(self,owner:str,*,authorized:bool)->CurriculumSnapshot:
        _owner(owner)
        if not authorized:raise PermissionError("private native curriculum requires owner")
        attempt_rows=self.lab.db.execute("""SELECT target_id,style,COUNT(*)
            FROM dragon_native_game_attempts WHERE owner=?
            GROUP BY target_id,style""",(owner,)).fetchall()
        # Only cryptographically verified native ROM structural evidence unlocks
        # later toolchain levels, not client claimed play, raw project count,
        # XP, label names or an unsigned arbitrary JSON report.
        proofs=self.evidence.history(owner,authorized=True) if self.evidence else ()
        built=set(x.target for x in proofs)
        attempts=Counter({(target,style):count for target,style,count in attempt_rows})
        successes=Counter(x.target for x in proofs)
        recommendations=[];blocked=[]
        for step in MILESTONES:
            # The introductory Game Boy source skill is already structurally
            # demonstrated. Do not farm repeat variants ahead of a newly
            # unlocked platforming/6502 skill.
            if step.milestone_id=="gb_input" and "game_boy" in built:
                continue
            unmet=tuple(x for x in step.requires if x not in built)
            if unmet:
                blocked.append({
                    "id":step.milestone_id,"target":step.target,
                    "requires":step.requires,"missing":unmet,
                    "reason":"trusted source-bound ROM structural receipts missing"
                })
                continue
            count=attempts[(step.target,step.genre)]
            if count>=self.lab.MAX_VARIANTS_PER_LESSON_TARGET_STYLE:
                continue
            # Prefer a genuinely new capability over farming 8 near-duplicates.
            score=step.weight-16*count
            if step.target in built:score-=8
            recommendations.append(CurriculumRecommendation(
                step.target,step.genre,step.milestone_id,
                ("New hardware/genre acquisition" if count==0 else
                 "Next bounded design iteration, still unverified"),
                score,count,successes[step.target]))
        recommendations.sort(key=lambda x:(-x.priority,x.target,x.genre))
        level=1+int("game_boy" in built)+int("nes" in built)+int(
            "game_boy_color" in built)
        return CurriculumSnapshot(
            owner,level,tuple(sorted(built)),sum(attempts.values()),
            tuple(recommendations),tuple(blocked),
            recommendations[0] if recommendations else None,
        )

    def generate_next(self,owner:str,*,authorized:bool,consent:bool,
                      now:float)->tuple[CurriculumSnapshot,object]:
        if not authorized or not consent:
            raise PermissionError("explicit owner consent required for next native exercise")
        before=self.evaluate(owner,authorized=True)
        selected=before.next_recommendation
        if selected is None:
            raise ValueError("no unlocked finite native exercise")
        record=self.lab.generate(
            owner,target_id=selected.target,style=selected.genre,
            authorized=True,consent=True,now=now)
        return self.evaluate(owner,authorized=True),record

def curriculum_report(result:CurriculumSnapshot)->dict:
    return asdict(result)
