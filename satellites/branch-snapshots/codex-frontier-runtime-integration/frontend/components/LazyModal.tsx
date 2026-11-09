/**
 * ╔══════════════════════════════════════════════════════════════════════════╗
 * ║    LazyModal — Thermal-Aware Modal Wrapper                              ║
 * ║                                                                          ║
 * ║    Only mounts modal children when visible, unmounts after close         ║
 * ║    Reduces memory footprint — 48 modals don't all stay in memory        ║
 * ║    Configurable unmount delay for smoother transitions                    ║
 * ╚══════════════════════════════════════════════════════════════════════════╝
 */

import React, { useState, useEffect, useRef, Suspense } from 'react';
import { View, ActivityIndicator, StyleSheet } from 'react-native';
import { ModalErrorBoundary } from './ModalErrorBoundary';

// Tiny centered spinner shown while a lazy modal chunk evaluates on first
// open (a few frames on a fast device; a touch longer on a cold S20). Gives
// the tap immediate feedback instead of a blank frame.
const LazyFallback = () => (
  <View style={lazyStyles.fallback}>
    <ActivityIndicator size="large" color="#a78bfa" />
  </View>
);
const lazyStyles = StyleSheet.create({
  fallback: {
    position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
    pointerEvents: 'none',
    alignItems: 'center', justifyContent: 'center',
    backgroundColor: 'rgba(6,10,20,0.6)',
  },
});

interface LazyModalProps {
  visible: boolean;
  /** Delay in ms before unmounting content after close (default: 500ms) */
  unmountDelay?: number;
  /** If true, never unmount once mounted (keep in memory for fast reopen) */
  keepMounted?: boolean;
  /** Human-readable name (used in error log + fallback UI). */
  name?: string;
  /** If the wrapped modal exposes onClose, pass it here so the error
   *  fallback can offer a "Close" rip-cord. */
  onClose?: () => void;
  /** Set false to disable the per-modal error boundary (default true). */
  errorBoundary?: boolean;
  children: React.ReactNode;
}

/**
 * Wraps a modal component to only render its content tree when visible.
 * After close, content is unmounted after a configurable delay,
 * freeing memory from heavy components like GameFactoryModal.
 *
 * Usage:
 *   <LazyModal visible={isOpen}>
 *     <HeavyModal visible={isOpen} onClose={close} />
 *   </LazyModal>
 */
// ── Global concurrent-modal cap (2026-06-24, per user request) ──────────
// Hard ceiling on how many modal trees may be mounted at once. Even though
// modals are lazy + auto-unmount, this is a memory safety net: if more than
// MAX are mounted (e.g. overlapping close-animations, or future keepMounted
// modals), the OLDEST modal that is no longer visible is force-unmounted.
// Prevents modal memory from ever stacking up on low-RAM devices (S20).
const MAX_CONCURRENT_MODALS = 20;
type ModalEntry = { id: number; visible: boolean; release: () => void };
const _mountedModals: ModalEntry[] = [];
let _modalIdSeq = 0;

function _evictExcessModals() {
  while (_mountedModals.length > MAX_CONCURRENT_MODALS) {
    // Evict the oldest entry that is NOT currently visible (never kill the
    // modal the user is actively looking at).
    const idx = _mountedModals.findIndex(e => !e.visible);
    if (idx < 0) break; // all visible — extremely unlikely; don't force-close
    const [victim] = _mountedModals.splice(idx, 1);
    try { victim.release(); } catch {}
  }
}
function _registerModal(entry: ModalEntry) {
  _mountedModals.push(entry);
  _evictExcessModals();
}
function _unregisterModal(id: number) {
  const i = _mountedModals.findIndex(e => e.id === id);
  if (i >= 0) _mountedModals.splice(i, 1);
}

export const LazyModal: React.FC<LazyModalProps> = ({
  visible,
  unmountDelay = 500,
  keepMounted = false,
  name,
  onClose,
  errorBoundary = true,
  children,
}) => {
  const [shouldMount, setShouldMount] = useState(false);
  const [everMounted, setEverMounted] = useState(false);
  const unmountTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const idRef = useRef<number>(++_modalIdSeq);
  const entryRef = useRef<ModalEntry | null>(null);

  useEffect(() => {
    if (visible) {
      // Cancel any pending unmount
      if (unmountTimer.current) {
        clearTimeout(unmountTimer.current);
        unmountTimer.current = null;
      }
      setShouldMount(true);
      setEverMounted(true);
    } else {
      if (keepMounted && everMounted) {
        // Keep mounted forever once opened
        return;
      }
      // Delay unmount so close animation can complete
      unmountTimer.current = setTimeout(() => {
        setShouldMount(false);
      }, unmountDelay);
    }

    return () => {
      if (unmountTimer.current) {
        clearTimeout(unmountTimer.current);
      }
    };
  }, [visible, unmountDelay, keepMounted, everMounted]);

  // Keep the global registry in sync — register on mount, update visibility,
  // unregister on unmount. The registry enforces the 20-modal ceiling.
  useEffect(() => {
    if (shouldMount) {
      if (!entryRef.current) {
        entryRef.current = {
          id: idRef.current,
          visible,
          release: () => { setShouldMount(false); setEverMounted(false); },
        };
        _registerModal(entryRef.current);
      } else {
        entryRef.current.visible = visible;
        _evictExcessModals();
      }
    } else if (entryRef.current) {
      _unregisterModal(entryRef.current.id);
      entryRef.current = null;
    }
  }, [shouldMount, visible]);

  useEffect(() => () => {
    if (entryRef.current) { _unregisterModal(entryRef.current.id); entryRef.current = null; }
  }, []);

  if (!shouldMount) return null;
  // Suspense lets children be React.lazy() modals — their heavy module code
  // is only evaluated on first open (staggered), not at hub.tsx module-eval.
  const content = <Suspense fallback={<LazyFallback />}>{children}</Suspense>;
  if (errorBoundary) {
    return (
      <ModalErrorBoundary name={name} onClose={onClose}>
        {content}
      </ModalErrorBoundary>
    );
  }
  return content;
};

export default LazyModal;
