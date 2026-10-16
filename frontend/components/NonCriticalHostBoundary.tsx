/**
 * Error containment for auxiliary root UI hosts.
 *
 * Toasts, connectivity banners and development overlays are not authority
 * holders. If one fails during render, keep the routed product alive instead
 * of sending the entire app into an unrelated safe-mode loop.
 */
import React from 'react';
import { traceStepSync } from '../utils/bootTracer';

type Props = { name: string; children: React.ReactNode };

export class NonCriticalHostBoundary extends React.Component<Props, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error) {
    try {
      const summary = String(error?.name || 'Error').slice(0, 40);
      traceStepSync(`aux_host_failed:${this.props.name}:${summary}`);
    } catch {
      // Diagnostics must never rethrow from a failure boundary.
    }
  }

  render() {
    return this.state.failed ? null : this.props.children;
  }
}

export default NonCriticalHostBoundary;
