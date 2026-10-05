/**
 * openModalFromRoute.ts (refactored 2026-02)
 * --------------------------------------------------------------
 * Helper that opens a modal — but prefers the dedicated native
 * route when one is registered in MODAL_TO_ROUTE.
 *
 *   • If the modal has a native route → router.push(route)
 *   • Otherwise → set the modalStore + router.push('/hub') so the
 *     legacy LazyModal tree picks it up.
 *
 * Usage:
 *   import { openModalFromRoute } from '../utils/openModalFromRoute';
 *   openModalFromRoute(router, 'achievements');   // → /achievements (route)
 *   openModalFromRoute(router, 'commandPalette'); // → /hub (legacy)
 */
import { useModalStore, ModalType, getRouteForModal } from '../store/modalStore';
import { recordEvent } from './modalLogger';
import type { Router } from 'expo-router';

export function openModalFromRoute(
  router: Pick<Router, 'push'>,
  modal: ModalType,
  data?: any,
): void {
  // 1. Check if a native route exists for this modal — preferred path.
  const nativeRoute = getRouteForModal(modal);
  if (nativeRoute) {
    try { recordEvent(String(modal), 'modal_to_route', 'info', { route: nativeRoute }); }
    catch { /* swallow */ }
    // Stash data so the native route can pull it via useModalStore.getModalData
    // if it needs the legacy modalData payload.
    if (data) useModalStore.getState().setModalData(String(modal), data);
    router.push(nativeRoute as any);
    return;
  }

  // 2. Legacy fallback: set the modalStore target + navigate to /hub.
  useModalStore.getState().openModal(modal, data);
  router.push('/hub' as any);
}

/** Alias matching the name suggested in earlier comments. */
export const openModalSmart = openModalFromRoute;
