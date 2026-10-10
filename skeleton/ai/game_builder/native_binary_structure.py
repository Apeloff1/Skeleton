"""Strict, bounded native game executable structural verification.

Examines *real* PE/COFF, ELF and thin 64-bit Mach-O images through one
no-follow, descriptor-relative file handle. Validates sections / loadable
segments, table boundaries, image type, architecture and executable entry
mapping. Does not execute code, recognize authentic toolchains, inspect all
malware, certify copyright status or authorize publication.

The ordinary intake's MZ/ELF/Mach-O prefix check is intentionally weaker.
Use this strict primitive when independently qualifying binary structure.
Unsupported executable variants fail closed; a loader may accept more forms.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import stat
import struct

from .native_release_intake import (
    NativeIntakeError, _MAX_BINARY, _no_follow, _open_directory,
)

_MAX_TABLE = 2 * 1024 * 1024
_MACHINE_PE = {0x014C:"x86", 0x8664:"x86_64", 0xAA64:"arm64", 0x01C4:"armv7"}
_MACHINE_ELF = {3:"x86", 62:"x86_64", 183:"arm64", 40:"armv7", 243:"riscv"}
_MACHINE_MACHO = {0x01000007:"x86_64", 0x0100000C:"arm64"}


class ExecutableFormatError(NativeIntakeError):
    """Native executable has unsafe or unsupported structural metadata."""


@dataclass(frozen=True, slots=True)
class ExecutableStructureReceipt:
    target_platform_id: str
    format_name: str
    architecture: str
    image_sha256: str
    image_size: int
    mapped_segments: int
    executable_segments: int
    entrypoint: int
    format_structure_checked: bool = True
    executable_boot_verified: bool = False
    compiler_origin_verified: bool = False
    malware_free_certified: bool = False
    legal_distribution_permitted: bool = False

    def __post_init__(self) -> None:
        if (
            self.target_platform_id not in {"windows_modern","linux_desktop","macos_modern"}
            or self.format_name not in {"PE/COFF","ELF","Mach-O"}
            or self.architecture not in {"x86","x86_64","arm64","armv7","riscv"}
            or not isinstance(self.image_sha256,str)
            or len(self.image_sha256)!=64
            or any(x not in "0123456789abcdef" for x in self.image_sha256)
            or type(self.image_size) is not int or not 256 <= self.image_size <= _MAX_BINARY
            or type(self.mapped_segments) is not int or not 1 <= self.mapped_segments <= 256
            or type(self.executable_segments) is not int or not 1 <= self.executable_segments <= self.mapped_segments
            or type(self.entrypoint) is not int or self.entrypoint < 0
        ):
            raise ExecutableFormatError("malformed native structural attestation")
        if any(getattr(self,flag) is not False for flag in (
            "executable_boot_verified","compiler_origin_verified",
            "malware_free_certified","legal_distribution_permitted",
        )):
            raise ExecutableFormatError("static binary parsing does not verify runtime, law or malware freedom")
        if self.format_structure_checked is not True:
            raise ExecutableFormatError("structural attestation cannot claim unchecked bytes")

    def public_receipt(self) -> dict[str, object]:
        return {
            "schema":"skeleton.game_builder.native_structure.v1",
            "target_platform_id":self.target_platform_id,
            "format_name":self.format_name,"architecture":self.architecture,
            "image_sha256":self.image_sha256,"image_size":self.image_size,
            "mapped_segments":self.mapped_segments,
            "executable_segments":self.executable_segments,
            "entrypoint":self.entrypoint,"format_structure_checked":True,
            "executable_boot_verified":False,"compiler_origin_verified":False,
            "malware_free_certified":False,"legal_distribution_permitted":False,
        }


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ExecutableFormatError(reason)


def _bounded_region(size: int, offset: int, count: int, *, maximum: int = _MAX_TABLE) -> None:
    _require(
        type(offset) is int and type(count) is int
        and 0 <= offset <= size and 0 <= count <= maximum
        and offset + count <= size,
        "executable header/table range escapes bounded native file",
    )


class _Reader:
    def __init__(self, fd: int, size: int):
        self.fd = fd
        self.size = size

    def at(self, offset: int, count: int) -> bytes:
        _bounded_region(self.size,offset,count)
        out = os.pread(self.fd,count,offset)
        _require(len(out) == count, "native executable was truncated during structure inspection")
        return out

    def unpack(self, fmt: str, offset: int) -> tuple:
        length = struct.calcsize(fmt)
        _require(length <= 256, "excessive native header field width")
        return struct.unpack(fmt, self.at(offset,length))


def _pe(reader: _Reader) -> tuple[str,int,int,int]:
    _require(reader.size >= 512 and reader.at(0,2)==b"MZ",
             "Windows release candidate must contain a PE/COFF image, not a DOS COM stub")
    (pe_at,) = reader.unpack("<I",0x3C)
    _bounded_region(reader.size,pe_at,24)
    _require(0x40 <= pe_at <= 1024 * 1024 and reader.at(pe_at,4)==b"PE\x00\x00",
             "invalid PE signature or DOS e_lfanew offset")
    machine,nsections,_,_,_,opt_size,flags=reader.unpack("<HHIIIHH",pe_at+4)
    _require(machine in _MACHINE_PE, "unsupported Windows executable architecture")
    _require(1 <= nsections <= 96, "PE requires bounded section table")
    _require(flags & 0x0002 != 0 and flags & 0x2000 == 0,
             "PE object is not an executable image or is a DLL")
    opt_at=pe_at+24
    _bounded_region(reader.size,opt_at,opt_size)
    (magic,) = reader.unpack("<H",opt_at)
    _require(magic in {0x10B,0x20B}, "unknown PE32/PE32+ optional header magic")
    _require(opt_size >= (112 if magic==0x20B else 96),
             "truncated Windows optional header")
    if machine in {0x8664,0xAA64}:
        _require(magic==0x20B, "64-bit Windows machine must use PE32+")
    (entry_rva,) = reader.unpack("<I",opt_at+16)
    (section_alignment,) = reader.unpack("<I",opt_at+32)
    (file_alignment,) = reader.unpack("<I",opt_at+36)
    (size_image,) = reader.unpack("<I",opt_at+56)
    (size_headers,) = reader.unpack("<I",opt_at+60)
    _require(0 < entry_rva < size_image and 0 < size_image <= 0x80000000,
             "PE entrypoint lies outside image")
    _require(file_alignment >= 512 and file_alignment <= 65536
             and file_alignment & (file_alignment-1)==0,
             "PE file alignment must be a supported power of two")
    _require(section_alignment >= file_alignment,
             "PE section alignment conflicts with file alignment")
    sec_table=opt_at+opt_size
    _bounded_region(reader.size,sec_table,nsections*40)
    _require(sec_table+nsections*40 <= size_headers <= reader.size,
             "PE section headers escape SizeOfHeaders or file")
    executable_sections=0
    raw_ranges=[]
    for idx in range(nsections):
        s=sec_table+idx*40
        virtual_size,virtual_rva,raw_size,raw_start=reader.unpack("<IIII",s+8)
        (properties,) = reader.unpack("<I",s+36)
        mapped=max(virtual_size,raw_size)
        _require(0 < mapped and virtual_rva < size_image
                 and virtual_rva + mapped <= size_image,
                 "PE section virtual span exceeds image")
        if raw_size:
            _bounded_region(reader.size,raw_start,raw_size,maximum=_MAX_BINARY)
            _require(raw_start >= size_headers
                     and raw_start % file_alignment == 0
                     and raw_size % file_alignment == 0,
                     "PE section file span overlaps headers or has invalid alignment")
            raw_ranges.append((raw_start,raw_start+raw_size))
        if properties & 0x20000000:
            executable_sections+=1
            if virtual_rva <= entry_rva < virtual_rva+mapped:
                entry_found=True
                # Catch malformed starts in a section with no code stored.
                _require(raw_size > 0, "PE entrypoint maps to empty executable section")
                break_after=False
    # Check ALL ranges; early return would miss a malicious appended section.
    for (a,b),(c,d) in zip(sorted(raw_ranges),sorted(raw_ranges)[1:]):
        _require(b<=c, "overlapping PE on-disk sections")
    _require(any(
        (lambda virtual_size,virtual_rva,raw_size,flags:
          flags & 0x20000000 and raw_size>0 and
          virtual_rva <= entry_rva < virtual_rva+max(virtual_size,raw_size))(
            *reader.unpack("<IIII",sec_table+i*40+8)[:3],
            reader.unpack("<I",sec_table+i*40+36)[0],
        ) for i in range(nsections)
    ), "Windows native entrypoint does not map to an executable section")
    return _MACHINE_PE[machine],nsections,executable_sections,entry_rva


def _elf(reader: _Reader) -> tuple[str,int,int,int]:
    ident=reader.at(0,16)
    _require(ident[:4]==b"\x7fELF", "not an ELF executable")
    cls,endian,version=ident[4:7]
    _require(cls in (1,2) and endian in (1,2) and version==1,
             "unsupported ELF class, endianness or version")
    endian_chr="<" if endian==1 else ">"
    is64=cls==2
    format_header=endian_chr+("HHIQQQIHHHHHH" if is64 else "HHIIIIIHHHHHH")
    full_size=64 if is64 else 52
    values=reader.unpack(format_header,16)
    etype,machine,elf_version,entry,phoff,shoff,flags,ehsize,phsize,phnum,shsize,shnum,shstr=values
    _require(ehsize==full_size and elf_version==1,
             "invalid ELF header size or version")
    _require(etype in (2,3), "native binary must be ELF executable or position-independent image")
    _require(machine in _MACHINE_ELF, "unsupported ELF CPU type")
    _require(entry!=0 and phoff>0 and 1<=phnum<=256
             and phsize==(56 if is64 else 32),
             "ELF executable needs bounded program headers and an entrypoint")
    _bounded_region(reader.size,phoff,phnum*phsize)
    _require(phoff>=ehsize, "ELF program header table overlaps ELF header")
    _require(shnum==0 or (shoff>0 and shsize==(64 if is64 else 40)),
             "ELF section header metadata contradictory")
    if shnum:
        _bounded_region(reader.size,shoff,shnum*shsize)
    executable=0
    loads=0
    found=False
    for idx in range(phnum):
        p=phoff+idx*phsize
        if is64:
            ptype,pflags,fileoff,vaddr,_,filesz,memsz,alignment=reader.unpack(
                endian_chr+"IIQQQQQQ",p
            )
        else:
            ptype,fileoff,vaddr,_,filesz,memsz,pflags,alignment=reader.unpack(
                endian_chr+"IIIIIIII",p
            )
        if ptype!=1:
            continue
        loads+=1
        _require(filesz<=memsz and memsz>0,"ELF load segment file size exceeds memory")
        _bounded_region(reader.size,fileoff,filesz,maximum=_MAX_BINARY)
        _require(not(alignment>1 and (alignment & (alignment-1))),
                 "ELF segment alignment is not a power of two")
        if alignment>1:
            _require(fileoff%alignment==vaddr%alignment,
                     "ELF load segment file/virtual address alignment differs")
        if pflags & 0x1:
            executable+=1
            if vaddr<=entry<vaddr+filesz:
                found=True
    _require(1<=loads<=256 and executable>0 and found,
             "ELF entrypoint does not reference an executable file-backed LOAD segment")
    return _MACHINE_ELF[machine],loads,executable,entry


def _macho(reader: _Reader) -> tuple[str,int,int,int]:
    magic=reader.at(0,4)
    _require(magic in (b"\xcf\xfa\xed\xfe",b"\xfe\xed\xfa\xcf"),
             "unsupported Mach-O format: strict validator accepts thin 64-bit images only")
    endian="<" if magic==b"\xcf\xfa\xed\xfe" else ">"
    cpu,subtype,filetype,ncmds,total_commands,flags,reserved=reader.unpack(
        endian+"IIIIIII",4
    )
    _require(cpu in _MACHINE_MACHO and filetype==2,
             "Mach-O target must be an executable for a supported CPU")
    _require(1<=ncmds<=256 and 8<=total_commands<=_MAX_TABLE,
             "Mach-O load-command budget exceeded")
    _bounded_region(reader.size,32,total_commands)
    position=32
    end=32+total_commands
    segment_count=0
    executables=0
    main_entry=None
    legacy_thread=False
    mapped=[]
    for _ in range(ncmds):
        _require(position+8<=end,"Mach-O load command list truncated")
        command,cmdsize=reader.unpack(endian+"II",position)
        _require(cmdsize>=8 and cmdsize%8==0 and position+cmdsize<=end,
                 "invalid Mach-O load command length or alignment")
        if command==0x19:  # LC_SEGMENT_64
            _require(cmdsize>=72, "truncated 64-bit Mach-O segment")
            vmaddr,vmsize,fileoff,filesz=reader.unpack(endian+"QQQQ",position+24)
            maxprot,initprot,nsections,flags=reader.unpack(endian+"IIII",position+56)
            _require(nsections<=512 and 72+80*nsections<=cmdsize,
                     "Mach-O declared section count exceeds segment command")
            _require(vmsize>=filesz and (filesz==0 or fileoff<=reader.size),
                     "Mach-O segment virtual memory shorter than file data")
            _bounded_region(reader.size,fileoff,filesz,maximum=_MAX_BINARY)
            segment_count+=1
            if initprot & 0x4:
                executables+=1
                if filesz:
                    mapped.append((fileoff,fileoff+filesz))
        elif command==0x80000028:  # LC_MAIN
            _require(cmdsize>=24, "truncated Mach-O LC_MAIN")
            _require(main_entry is None,"duplicate Mach-O main entry command")
            main_entry,stacksize=reader.unpack(endian+"QQ",position+8)
        elif command in (0x4,0x5): # LC_THREAD/LC_UNIXTHREAD
            legacy_thread=True
        position+=cmdsize
    _require(position==end and segment_count>0 and executables>0,
             "Mach-O truncated command list or no executable segment")
    _require(main_entry is not None or legacy_thread,
             "Mach-O has no LC_MAIN or native thread entry")
    if main_entry is not None:
        _require(any(start<=main_entry<finish for start,finish in mapped),
                 "Mach-O LC_MAIN entry is outside file-backed executable segments")
    return _MACHINE_MACHO[cpu],segment_count,executables,main_entry if main_entry is not None else 0


def verify_native_executable_structure(
    path: str | Path, *, target_platform_id: str, expected_sha256: str,
) -> ExecutableStructureReceipt:
    """Parse actual binary data and independently rehash through one pinned fd.

    Valid format structure is not proof of successful compilation, working
    gameplay, malware freedom or rights-holder / publisher authorization.
    """
    if not isinstance(expected_sha256,str) or len(expected_sha256)!=64 or any(
        character not in "0123456789abcdef" for character in expected_sha256
    ):
        raise ExecutableFormatError("a trusted expected executable digest is mandatory")
    if target_platform_id not in {"windows_modern","linux_desktop","macos_modern"}:
        raise ExecutableFormatError("unsupported native structural target")
    path=Path(path)
    directory=_open_directory(path.parent)
    try:
        try:
            fd=os.open(path.name,os.O_RDONLY|_no_follow()|getattr(os,"O_CLOEXEC",0)
                       |getattr(os,"O_NONBLOCK",0),dir_fd=directory)
        except OSError as exc:
            raise ExecutableFormatError("executable cannot be safely opened") from exc
        try:
            initial=os.fstat(fd)
            _require(stat.S_ISREG(initial.st_mode) and initial.st_nlink==1
                     and 256<=initial.st_size<=_MAX_BINARY,
                     "native executable must be a unique bounded regular file")
            r=_Reader(fd,initial.st_size)
            kind={"windows_modern":"PE/COFF","linux_desktop":"ELF",
                  "macos_modern":"Mach-O"}[target_platform_id]
            if kind=="PE/COFF":
                arch,segments,execs,entry=_pe(r)
            elif kind=="ELF":
                arch,segments,execs,entry=_elf(r)
            else:
                arch,segments,execs,entry=_macho(r)
            h=sha256()
            count=0
            while count<=_MAX_BINARY:
                part=os.pread(fd,min(256*1024, _MAX_BINARY+1-count),count)
                if not part:
                    break
                h.update(part)
                count+=len(part)
            final=os.fstat(fd)
            _require(count==initial.st_size and count==final.st_size and
                     (initial.st_dev,initial.st_ino,initial.st_mtime_ns,initial.st_ctime_ns)
                     ==(final.st_dev,final.st_ino,final.st_mtime_ns,final.st_ctime_ns),
                     "native image modified while validating structure or hashing")
            _require(h.hexdigest()==expected_sha256,
                     "native executable bytes differ from independently reviewed artifact")
            return ExecutableStructureReceipt(
                target_platform_id,kind,arch,h.hexdigest(),count,segments,execs,entry,
            )
        except OSError as exc:
            raise ExecutableFormatError("native executable structure reader failed") from exc
        finally:
            os.close(fd)
    finally:
        os.close(directory)
