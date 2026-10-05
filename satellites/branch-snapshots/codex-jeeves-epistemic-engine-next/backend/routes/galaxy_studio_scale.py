"""
╔══════════════════════════════════════════════════════════════════════════╗
║  GALAXY STUDIO — SCALE PARSER (extracted 2026-06 to shrink the monolith)  ║
║                                                                            ║
║  Pure natural-language → build-scale translation. No state, no DB, no      ║
║  circular import back into galaxy_studio.py. The owning module imports     ║
║  `_parse_scale` (used by /create + /expand) and `_scale_label`.            ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
import re


def _parse_scale(scale_text: str, target_files: int = 0, target_size_gb: float = 0) -> dict:
    """Parse natural language scale descriptions into build parameters.

    Examples:
    - "500,000 assets and a 25gb game" -> { files: 500000, size_gb: 25 }
    - "build me a massive 100gb AAA game" -> { files: ~1000000, size_gb: 100 }
    - "competitor to Elden Ring" -> { files: ~250000, size_gb: 50 }
    """
    text = scale_text.lower().replace(",", "").replace("_", "") if scale_text else ""

    parsed_files = target_files
    parsed_size = target_size_gb

    # Parse file/asset counts
    asset_patterns = [
        r'(\d+)\s*(?:k|thousand)\s*(?:files?|assets?)',
        r'(\d+)\s*(?:m|million)\s*(?:files?|assets?)',
        r'(\d+)\s*(?:files?|assets?)',
    ]
    for pattern in asset_patterns:
        m = re.search(pattern, text)
        if m:
            num = int(m.group(1))
            if 'million' in text or 'm ' in text[m.start():m.end()+5]:
                parsed_files = max(parsed_files, num * 1_000_000)
            elif 'thousand' in text or 'k ' in text[m.start():m.end()+5]:
                parsed_files = max(parsed_files, num * 1_000)
            else:
                parsed_files = max(parsed_files, num)

    # Parse size
    size_patterns = [
        r'(\d+(?:\.\d+)?)\s*(?:gb|gigabyte)',
        r'(\d+(?:\.\d+)?)\s*(?:tb|terabyte)',
        r'(\d+(?:\.\d+)?)\s*(?:mb|megabyte)',
    ]
    for i, pattern in enumerate(size_patterns):
        m = re.search(pattern, text)
        if m:
            num = float(m.group(1))
            if i == 0: parsed_size = max(parsed_size, num)          # GB
            elif i == 1: parsed_size = max(parsed_size, num * 1000) # TB
            elif i == 2: parsed_size = max(parsed_size, num / 1000) # MB

    # Parse AAA game references for implicit scale
    aaa_refs = {
        'elden ring': (250_000, 50), 'gta': (500_000, 100), 'red dead': (400_000, 120),
        'cyberpunk': (300_000, 70), 'witcher': (200_000, 50), 'skyrim': (250_000, 40),
        'zelda': (150_000, 30), 'god of war': (200_000, 60), 'horizon': (250_000, 80),
        'assassin': (300_000, 70), 'call of duty': (400_000, 150), 'final fantasy': (200_000, 90),
        'massive': (100_000, 25), 'enormous': (200_000, 50), 'gigantic': (300_000, 75),
        'colossal': (500_000, 100), 'infinite': (1_000_000, 200),
    }
    for ref, (f, s) in aaa_refs.items():
        if ref in text:
            parsed_files = max(parsed_files, f)
            parsed_size = max(parsed_size, s)

    # Default: if nothing parsed, use unlimited AAA defaults
    if parsed_files == 0:
        parsed_files = 0  # 0 means "generate all categories at full depth"
    if parsed_size == 0:
        parsed_size = 0  # 0 means "no size target, just max quality"

    # Calculate scale multiplier — AGGRESSIVE, ALWAYS USE LARGER
    file_mult = max(10, parsed_files // 100) if parsed_files > 0 else 10
    size_mult = max(10, int(parsed_size * 100)) if parsed_size > 0 else 10  # 100 multiplier per GB
    multiplier = max(file_mult, size_mult)  # Always use the LARGER multiplier

    # Target files: derive from multiplier if not explicitly set
    effective_files = parsed_files
    if effective_files == 0:
        effective_files = multiplier * 500  # 500 files per multiplier unit
    # If size implies more files than parsed_files, boost
    if parsed_size > 0:
        size_implied_files = int(parsed_size * 20_000)  # 20K files per GB
        effective_files = max(effective_files, size_implied_files)

    # ─── HARD FLOOR: every build delivers ≥ 48 000 files (user requirement) ───
    # No matter what the user typed (or didn't type) we never ship a build
    # below 48 000 generated files. This guarantees the "JUGGERNAUT-tier"
    # baseline shipping experience and matches the user's explicit minimum.
    MIN_FILES_FLOOR = 48_000
    effective_files = max(effective_files, MIN_FILES_FLOOR)

    return {
        "target_files": effective_files,
        "target_size_gb": parsed_size,
        "multiplier": multiplier,
        "scale_label": _scale_label(effective_files, parsed_size),
    }


def _scale_label(files: int, size_gb: float) -> str:
    if files >= 1_000_000 or size_gb >= 100: return "TITAN"
    if files >= 500_000 or size_gb >= 50: return "COLOSSUS"
    if files >= 100_000 or size_gb >= 25: return "LEVIATHAN"
    if files >= 50_000 or size_gb >= 10: return "BEHEMOTH"
    if files >= 10_000 or size_gb >= 5: return "JUGGERNAUT"
    if files >= 1_000 or size_gb >= 1: return "FORGE"
    return "UNLIMITED"
