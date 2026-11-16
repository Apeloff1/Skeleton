/**
 * shareResult.ts — Cross-platform share / copy helper used by power routes.
 * On native, hands off to the RN Share API. On web, falls back to the
 * navigator.clipboard text-copy path with a graceful toast.
 *
 * 2026-02 — Migrated from blocking Alert.alert to non-blocking Toast.
 */
import { Share, Platform } from 'react-native';
import { toast } from '../components/Toast';

export async function shareResult(text: string, title = 'CodeDock result') {
  if (!text) return;
  if (Platform.OS === 'web') {
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const nav: any = typeof navigator !== 'undefined' ? navigator : null;
      if (nav?.share) {
        await nav.share({ text, title });
        return;
      }
      if (nav?.clipboard?.writeText) {
        await nav.clipboard.writeText(text);
        toast.success('Copied to clipboard');
        return;
      }
    } catch {}
    toast.warn('Share unavailable — long-press to copy');
    return;
  }
  try {
    await Share.share({ message: text, title });
  } catch (e: any) {
    toast.error(`Share failed: ${e?.message || 'unknown error'}`);
  }
}

export async function copyToClipboard(text: string, label = 'Copied to clipboard') {
  if (!text) return;
  try {
    if (Platform.OS === 'web' && typeof navigator !== 'undefined' && (navigator as any)?.clipboard) {
      await (navigator as any).clipboard.writeText(text);
      toast.success(label);
      return;
    }
    // Native — dynamically import expo-clipboard if available
    try {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const Clipboard = require('expo-clipboard');
      await Clipboard.setStringAsync(text);
      toast.success(label);
    } catch {
      // Fallback: share-sheet
      await Share.share({ message: text });
    }
  } catch {
    // swallow — caller can decide to surface a warning
  }
}
