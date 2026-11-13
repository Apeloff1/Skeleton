/**
 * Notes Filters Store — keeps the /notes screen's transient filter state
 * (search query, future category, future tag) in a global Zustand store
 * so:
 *   1. Deep-link callers (e.g. dashboard widgets, command palette) can
 *      navigate to /notes and pre-set a search/filter in one shot.
 *   2. The "clear all filters" affordance is a single helper instead of
 *      duplicated across every empty-state CTA.
 *
 * This is intentionally *not* persisted — filters reset on app cold start.
 */
import { create } from 'zustand';

export interface NotesFiltersState {
  /** Free-text search query. */
  search: string;
  /** Future-proofed slot — currently unused. */
  category: string | null;
  /** Future-proofed slot — currently unused. */
  tag: string | null;
  /** Set helpers — flat to keep call-sites short. */
  setSearch: (s: string) => void;
  setCategory: (c: string | null) => void;
  setTag: (t: string | null) => void;
  /** Single chokepoint for "show every note again". */
  clearAllFilters: () => void;
  /** True when *any* filter is active — for showing "Clear" CTAs. */
  hasActiveFilters: () => boolean;
}

export const useNotesFilters = create<NotesFiltersState>((set, get) => ({
  search: '',
  category: null,
  tag: null,

  setSearch: (s) => set({ search: s }),
  setCategory: (c) => set({ category: c }),
  setTag: (t) => set({ tag: t }),

  clearAllFilters: () => set({ search: '', category: null, tag: null }),

  hasActiveFilters: () => {
    const { search, category, tag } = get();
    return Boolean(search) || category !== null || tag !== null;
  },
}));

/**
 * Imperative helper for callers outside React (e.g. command palette,
 * deep-link handlers). Sets the filter then a navigator can router.push('/notes').
 */
export function setNotesSearchImperative(s: string) {
  useNotesFilters.getState().setSearch(s);
}

/** Used by external links/buttons to wipe state before routing. */
export function clearNotesFiltersImperative() {
  useNotesFilters.getState().clearAllFilters();
}
