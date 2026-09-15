#!/usr/bin/env python3
"""One-shot guarded repair for strict frontend typecheck debt.

Every edit is an exact one-occurrence replacement. If concurrent work changes a
target unexpectedly, the script fails instead of guessing or overwriting it.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(relative: str, old: str, new: str) -> None:
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{relative}: expected exactly one match, found {count}: {old[:100]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"patched {relative}")


def main() -> None:
    replace_once(
        "frontend/app/hub.tsx",
        """const lazyNamed = (loader: () => Promise<any>, key: string) =>\n  React.lazy(() => loader().then((m: any) => ({ default: m[key] })));""",
        """type LazyComponentExport<T> = T extends React.ComponentType<infer P>\n  ? React.ComponentType<P>\n  : React.ComponentType<any>;\n\nconst lazyNamed = <TModule, TKey extends keyof TModule>(\n  loader: () => Promise<TModule>,\n  key: TKey,\n): React.LazyExoticComponent<LazyComponentExport<TModule[TKey]>> =>\n  React.lazy(async () => {\n    const module = await loader();\n    return { default: module[key] as LazyComponentExport<TModule[TKey]> };\n  });""",
    )

    replace_once(
        "frontend/app/command-center.tsx",
        "pipe[gf.id].stages.map((s) => (",
        "pipe[gf.id].stages.map((s: { key: string; icon: string; order: number; label: string; passed: boolean; score: string | number; report?: { note?: string } }) => (",
    )

    for relative in ("frontend/app/construct-forge.tsx", "frontend/app/forge.tsx"):
        replace_once(relative, "onSelectPart={(i) => setSelectedPart(i)}", "onSelectPart={(i: number) => setSelectedPart(i)}")

    replace_once(
        "frontend/app/forge.tsx",
        "  capacity: { color: C.muted, fontSize: 11, textAlign: 'center', marginTop: 14 },",
        """  dnaCard: { backgroundColor: C.card, borderWidth: 1, borderColor: C.border, borderRadius: 14, padding: 12, marginTop: 12 },\n  dnaHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },\n  dnaTitle: { color: C.text, fontSize: 13, fontWeight: '900', flex: 1 },\n  dnaCopy: { borderWidth: 1, borderColor: C.accent, borderRadius: 9, paddingHorizontal: 10, paddingVertical: 6 },\n  dnaCopyTxt: { color: C.accent, fontSize: 10, fontWeight: '900' },\n  dnaHex: { color: C.muted, fontSize: 10, fontFamily: 'monospace', marginTop: 8 },\n  ecsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 8 },\n  ecsChip: { backgroundColor: C.alt, borderWidth: 1, borderColor: C.border, borderRadius: 999, paddingHorizontal: 9, paddingVertical: 4 },\n  ecsChipTxt: { color: C.text, fontSize: 10, fontWeight: '700' },\n  dnaPruned: { color: '#F59E0B', fontSize: 10, fontWeight: '700', marginTop: 8 },\n  capacity: { color: C.muted, fontSize: 11, textAlign: 'center', marginTop: 14 },""",
    )

    vault_block = """  const loadVaultPkgs = React.useCallback(async () => {\n    const r = await api.get<any>(`${WF}/vault?limit=25`, { timeoutMs: 15000 });\n    if (r.ok && r.data?.ok) setVaultPkgs(r.data.packages || []);\n  }, []);\n\n"""
    replace_once("frontend/app/gameforge-studio.tsx", vault_block, "")
    replace_once(
        "frontend/app/gameforge-studio.tsx",
        "  React.useEffect(() => { loadOverview(); }, [loadOverview]);",
        vault_block + "  React.useEffect(() => { loadOverview(); }, [loadOverview]);",
    )

    replace_once(
        "frontend/app/menu.tsx",
        "  id: ModalType | string;",
        "  id: Exclude<ModalType, null> | string;",
    )
    replace_once(
        "frontend/app/menu.tsx",
        "onPress: () => toast.info(`${card.title} · category lookup → ${card.desc}`, { durationMs: 4500 }),",
        "onPress: () => { toast.info(`${card.title} · category lookup → ${card.desc}`, { durationMs: 4500 }); },",
    )

    replace_once(
        "frontend/app/playable.tsx",
        """  repair_attempts?: number; evaluation?: Evaluation; parent_id?: string | null;\n  tweak?: string; intricacy?: number; repair_trail?: any[];""",
        """  repair_attempts?: number; evaluation?: Evaluation; parent_id?: string | null;\n  tweak?: string; intricacy?: number; repair_trail?: any[];\n  reactions?: Record<string, number>; version?: number | string; remix_count?: number; derive_mode?: string;""",
    )

    replace_once(
        "frontend/app/settings/index.tsx",
        "useState<{ disk_mb: number; raw_mb: number; saved_mb: number; compression_ratio: number; zstd_level: number; builds: number; total_files: number; keep_target: number } | null>(null)",
        "useState<{ disk_mb: number; raw_mb: number; saved_mb: number; compression_ratio: number; zstd_level: number; builds: number; total_files: number; keep_target: number; newest_build_id?: string | null } | null>(null)",
    )

    replace_once(
        "frontend/features/MegaAcademy/MegaAcademyModal.tsx",
        """      const ctx = tab === 'quizzes' ? 'quiz_nudge'\n                : tab === 'lessons' ? 'lesson'\n                : tab === 'challenges' ? 'code_walkthrough'\n                : 'lesson';""",
        """      const ctx = tab === 'quizzes' ? 'quiz_nudge'\n                : tab === 'challenges' ? 'code_walkthrough'\n                : 'lesson';""",
    )

    print("guarded frontend type repair complete")


if __name__ == "__main__":
    main()
