import AsyncStorage from '@react-native-async-storage/async-storage';

export type ValueEntry = {
  id: string;
  amount: number;
  note: string;
  createdAt: string;
};

export type WealthSnapshot = {
  entries: ValueEntry[];
};

const KEY = '@codedock:wealth:v2';

export async function loadWealth(): Promise<WealthSnapshot> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    if (!raw) return { entries: [] };
    const parsed = JSON.parse(raw) as Partial<WealthSnapshot>;
    return {
      entries: Array.isArray(parsed.entries)
        ? parsed.entries
            .filter(entry => Number.isFinite(entry?.amount))
            .slice(0, 500)
        : [],
    };
  } catch {
    return { entries: [] };
  }
}

export async function saveWealth(snapshot: WealthSnapshot): Promise<void> {
  await AsyncStorage.setItem(KEY, JSON.stringify({ entries: snapshot.entries.slice(0, 500) }));
}

export function createValueEntry(amount: number, note: string): ValueEntry {
  const now = new Date();
  return {
    id: `${now.getTime()}-${Math.random().toString(36).slice(2, 8)}`,
    amount,
    note: note.trim(),
    createdAt: now.toISOString(),
  };
}

export function totalValue(entries: readonly ValueEntry[]): number {
  return entries.reduce((sum, entry) => sum + Number(entry.amount || 0), 0);
}
