"""Native SDL PC ABI contract: correct OS/CPU, no fake cross-platform builds."""
from __future__ import annotations
from dataclasses import asdict,dataclass
import json,re

@dataclass(frozen=True)
class DesktopABI:
    id:str
    system:str
    arch:str
    runner:str
    input:str
    output:str
    notes:str

BASE_DESKTOP=frozenset(("pc_linux","pc_windows","pc_macos","steam_deck"))
ABI_PROFILES={
"windows_10":("Windows","x86_64","windows-2025","SDL2 XInput","exe","Windows 10 minimum"),
"windows_11":("Windows","x86_64","windows-2025","SDL2 XInput","exe","Windows 11 desktop"),
"windows_arm64":("Windows","arm64","windows-11-arm64","SDL2 XInput","exe","ARM64 native Windows SDK"),
"macos_intel":("Darwin","x86_64","macos-15-intel","SDL2 HID","mach_o","Intel Mach-O only"),
"macos_apple_silicon":("Darwin","arm64","macos-15","SDL2 HID","mach_o","Apple Silicon Mach-O"),
"linux_arm64":("Linux","arm64","ubuntu-24.04-arm","SDL2 gamepad","elf","native ARM64 Linux"),
"linux_riscv64":("Linux","riscv64","external-riscv-runner","SDL2 gamepad","elf","RISC-V runner required"),
"linux_x86_32":("Linux","x86","external-i686-runner","SDL2 gamepad","elf","32-bit SDL2 libraries"),
"freebsd_amd64":("FreeBSD","x86_64","external-freebsd","SDL2 gamepad","elf","FreeBSD native build"),
"freebsd_arm64":("FreeBSD","arm64","external-freebsd-arm","SDL2 gamepad","elf","FreeBSD native ARM64"),
"openbsd_amd64":("OpenBSD","x86_64","external-openbsd","SDL2/sndio","elf","OpenBSD native audio"),
"netbsd_amd64":("NetBSD","x86_64","external-netbsd","SDL2","elf","NetBSD native SDL2"),
"raspberry_pi_4":("Linux","arm64","external-pi4","SDL2 USB gamepad","elf","ARM64 Pi OS required"),
"raspberry_pi_5":("Linux","arm64","external-pi5","SDL2 USB gamepad","elf","native Pi5 graphics test"),
"steam_machine":("Linux","x86_64","external-steamos","Steam Input SDL2","elf","Steamos hardware pending"),
"chromeos_x86":("Linux","x86_64","external-crostini","SDL2 Crostini","elf","Crostini Linux, not ChromeOS native"),
"chromeos_arm":("Linux","arm64","external-crostini","SDL2 Crostini","elf","ARM Linux container"),
"asus_rog_ally":("Windows","x86_64","windows-2025","SDL2 handheld","exe","ROG Ally control tests pending"),
"lenovo_legion_go":("Windows","x86_64","windows-2025","SDL2 handheld","exe","detachable pad tests pending"),
"msi_claw":("Windows","x86_64","windows-2025","SDL2 handheld","exe","input/battery tests pending"),
"gpd_win":("Windows","x86_64","windows-2025","SDL2 handheld","exe","GPD controls pending"),
}
ABI_PROFILES={k:DesktopABI(k,*v) for k,v in ABI_PROFILES.items()}
DESKTOP_NATIVE=BASE_DESKTOP|frozenset(ABI_PROFILES)
CPU_PATTERNS={
"arm64":r"^(aarch64|arm64|ARM64)$",
"x86_64":r"^(x86_64|AMD64|amd64)$",
"x86":r"^(i386|i486|i586|i686|x86|X86)$",
"riscv64":r"^(riscv64|RISCV64)$",
}
def apply_desktop_abi(target_id:str,files:dict[str,str])->dict[str,str]:
    if target_id not in ABI_PROFILES:
        raise ValueError("unrecognized native PC ABI")
    p=ABI_PROFILES[target_id]
    if not isinstance(files,dict) or not isinstance(files.get("CMakeLists.txt"),str):
        raise ValueError("SDL project CMake output required")
    cmake=files["CMakeLists.txt"]
    patched,n=re.subn(r"(?m)^(project\([^\n]+\)\n)",
        lambda m:m.group(1)+"include(cmake/dragon_target_contract.cmake)\n",
        cmake,count=1)
    if n!=1 or len(patched)>120000:
        raise ValueError("CMake ABI insertion failed")
    contract=(
        "# Generated native ABI check; required native compiler & SDK external\n"
        f'set(DRAGON_EXPECTED_SYSTEM "{p.system}")\n'
        f'set(DRAGON_EXPECTED_ARCH "{p.arch}")\n'
        'if(NOT CMAKE_SYSTEM_NAME STREQUAL DRAGON_EXPECTED_SYSTEM)\n'
        '  message(FATAL_ERROR "Dragon requested native OS is not the configured build target")\n'
        'endif()\n'
        f'if(NOT CMAKE_SYSTEM_PROCESSOR MATCHES "{CPU_PATTERNS[p.arch]}")\n'
        '  message(FATAL_ERROR "Dragon native ABI architecture mismatch")\n'
        'endif()\n'
    )
    out=dict(files)
    out["CMakeLists.txt"]=patched
    out["cmake/dragon_target_contract.cmake"]=contract
    out["dragon-desktop-abi.json"]=json.dumps({
       "schema":"skeleton.ai.dragon.desktop_abi.v1",**asdict(p),
       "compiled":False,"device_verified":False,
       "controller_verified":False,"signed_package":False
    },sort_keys=True,indent=2)+"\n"
    out["README.abi.md"]=(
        "# Original Dragon target-specific desktop game\n\n"
        f"System {p.system}; CPU ABI {p.arch}. {p.notes}. "
        f"Controls: {p.input}. Required runner: {p.runner}. "
        "CMake rejects wrong OS/CPU ABI; supply genuine target-native "
        "or verified cross compiler and SDL2. Source only until compiled, "
        "executed, hardware-controller tested and legally packaged.\n"
    )
    return out
