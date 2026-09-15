/**
 * 🎨 APP SKINS — 30-skin large-scale reskinner. Default: "hyperwave".
 * Each skin overrides the live palette keys read across the app (theme.colors.*).
 * Applied at runtime by src/utils/skinStore.ts.
 */
export type SkinColors = {
  bg: string; bgElevated: string; bgSubtle: string;
  primary: string; primaryHover: string; primarySoft: string; borderFocus: string;
  accentCyan: string; accentPink: string; accentGold: string;
};
export type Skin = { id: string; name: string; emoji: string; colors: SkinColors };

const mk = (
  id: string, name: string, emoji: string,
  bg: string, bg2: string, primary: string, hover: string,
  cyan: string, pink: string, gold: string,
): Skin => ({
  id, name, emoji,
  colors: {
    bg, bgElevated: bg2, bgSubtle: bg2,
    primary, primaryHover: hover, primarySoft: primary + '28', borderFocus: primary,
    accentCyan: cyan, accentPink: pink, accentGold: gold,
  },
});

export const DEFAULT_SKIN = 'hyperwave';

export const SKINS: Skin[] = [
  mk('hyperwave', 'Hyperwave', '🌌', '#0b0820', '#15103a', '#c026d3', '#e879f9', '#3B82F6', '#f472b6', '#fbbf24'),
  mk('midnight', 'Midnight', '🌑', '#070910', '#10131f', '#3b82f6', '#60a5fa', '#60A5FA', '#818cf8', '#fcd34d'),
  mk('aurora', 'Aurora', '🌠', '#04130f', '#082018', '#10b981', '#34d399', '#3B82F6', '#a3e635', '#fde047'),
  mk('ember', 'Ember', '🔥', '#170a06', '#23110a', '#f97316', '#fb923c', '#fbbf24', '#f87171', '#fde68a'),
  mk('forest', 'Forest', '🌲', '#08120b', '#0e1d13', '#22c55e', '#4ade80', '#60A5FA', '#a3e635', '#facc15'),
  mk('mono', 'Mono', '⬜', '#0a0a0a', '#161616', '#d4d4d4', '#fafafa', '#a3a3a3', '#737373', '#e5e5e5'),
  mk('sakura', 'Sakura', '🌸', '#1a0d14', '#26121d', '#ec4899', '#f472b6', '#f9a8d4', '#c084fc', '#fbcfe8'),
  mk('oceanic', 'Oceanic', '🌊', '#04121a', '#072030', '#3B82F6', '#60A5FA', '#3B82F6', '#60A5FA', '#93C5FD'),
  mk('neon', 'Neon', '💚', '#060d06', '#0c180c', '#84cc16', '#a3e635', '#3B82F6', '#f0abfc', '#fde047'),
  mk('sunset', 'Sunset', '🌇', '#1a0a0f', '#27101a', '#fb7185', '#fda4af', '#fb923c', '#c084fc', '#fcd34d'),
  mk('glacier', 'Glacier', '🧊', '#080f17', '#0e1a26', '#93C5FD', '#BFDBFE', '#93C5FD', '#c4b5fd', '#DBEAFE'),
  mk('vapor', 'Vapor', '🪐', '#0f0a1a', '#1a1130', '#a78bfa', '#c4b5fd', '#3B82F6', '#f0abfc', '#fde68a'),
  mk('goldnoir', 'Gold Noir', '🪙', '#0c0a06', '#17130a', '#f5c451', '#fcd34d', '#d4a373', '#fbbf24', '#fde68a'),
  mk('matrix', 'Matrix', '🟩', '#020a04', '#06140a', '#22c55e', '#4ade80', '#16a34a', '#15803d', '#86efac'),
  mk('crimson', 'Crimson', '🩸', '#150407', '#23070c', '#ef4444', '#f87171', '#fb7185', '#fb923c', '#fca5a5'),
  mk('lavender', 'Lavender', '💜', '#100c1a', '#1b1430', '#8b5cf6', '#a78bfa', '#c4b5fd', '#f0abfc', '#ddd6fe'),
  mk('coffee', 'Coffee', '☕', '#120c08', '#1e150d', '#b45309', '#d97706', '#f59e0b', '#a16207', '#fcd34d'),
  mk('arctic', 'Arctic', '❄️', '#0a0f14', '#121b24', '#60A5FA', '#93C5FD', '#BFDBFE', '#c4b5fd', '#DBEAFE'),
  mk('toxic', 'Toxic', '☢️', '#0a0f02', '#141d06', '#a3e635', '#bef264', '#3B82F6', '#f0abfc', '#fde047'),
  mk('royal', 'Royal', '👑', '#080a1a', '#0f1330', '#6366f1', '#818cf8', '#3B82F6', '#c084fc', '#fbbf24'),
  mk('peach', 'Peach', '🍑', '#1a0f0a', '#281913', '#fb923c', '#fdba74', '#f472b6', '#fcd34d', '#fed7aa'),
  mk('slate', 'Slate', '🪨', '#0a0c0f', '#141820', '#64748b', '#94a3b8', '#60A5FA', '#a78bfa', '#cbd5e1'),
  mk('mint', 'Mint', '🌿', '#06120e', '#0b1f18', '#60A5FA', '#93C5FD', '#3B82F6', '#a3e635', '#BFDBFE'),
  mk('blood', 'Blood Moon', '🌕', '#140505', '#220909', '#dc2626', '#ef4444', '#f97316', '#a855f7', '#fbbf24'),
  mk('cyber', 'Cyber', '🤖', '#080612', '#100c22', '#2563EB', '#3B82F6', '#e879f9', '#f0abfc', '#fde047'),
  mk('dune', 'Dune', '🏜️', '#120e07', '#1f180d', '#d97706', '#f59e0b', '#fbbf24', '#ea580c', '#fde68a'),
  mk('nebula', 'Nebula', '✨', '#0b0718', '#150e2c', '#a855f7', '#c084fc', '#3B82F6', '#f472b6', '#fcd34d'),
  mk('rosegold', 'Rose Gold', '🌹', '#160c0f', '#23131a', '#fda4af', '#fecdd3', '#f9a8d4', '#fbbf24', '#fde68a'),
  mk('obsidian', 'Obsidian', '⬛', '#050507', '#0d0d12', '#818cf8', '#a5b4fc', '#60A5FA', '#c084fc', '#e5e7eb'),
  mk('citrus', 'Citrus', '🍋', '#0f1003', '#1b1d06', '#eab308', '#facc15', '#84cc16', '#f97316', '#fde047'),
];

export const SKIN_BY_ID: Record<string, Skin> = Object.fromEntries(SKINS.map((s) => [s.id, s]));
