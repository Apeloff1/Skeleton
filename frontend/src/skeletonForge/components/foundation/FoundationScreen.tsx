/**
 * Live studio screen. Project builds go through useForgeRun, and cockpit
 * STATUS goes through useCockpitConsole — the same owners as the forge
 * cockpit, not a second poller.
 */
import React from 'react';
import { AccessibilityInfo, PixelRatio, Platform } from 'react-native';
import { gameforgeAuthPort } from '../../foundation/authPort';
import type { A11yPlatformSnapshot } from '../../foundation/a11y';
import type { PersistSnapshot } from '../../foundation/model';
import { asyncStorageKv } from '../../foundation/storageDevice';
import { loadFoundation, saveFoundation } from '../../foundation/storage';
import { composeSummaryOf, consoleFailures } from '../../cockpitScreen';
import { useCockpitConsole } from '../../consoleHooks';
import { useForgeCatalog, useForgeRun, useLiveCompose, useNow } from '../../hooks';
import useReduceMotion from '../../../hooks/useReduceMotion';
import FoundationShell from './FoundationShell';

function usePlatformA11y(): A11yPlatformSnapshot {
  const systemReducedMotion = useReduceMotion();
  const [motionSupported, setMotionSupported] = React.useState(false);
  const [systemTextScale, setSystemTextScale] = React.useState<number | null>(null);
  React.useEffect(() => {
    let supported = false;
    if (typeof AccessibilityInfo?.isReduceMotionEnabled === 'function') supported = true;
    if (Platform.OS === 'web' && typeof window !== 'undefined' && typeof window.matchMedia === 'function') supported = true;
    setMotionSupported(supported);
    if (Platform.OS !== 'web' && typeof PixelRatio.getFontScale === 'function') {
      const scale = PixelRatio.getFontScale();
      if (typeof scale === 'number' && Number.isFinite(scale)) setSystemTextScale(scale);
    }
  }, []);
  return { motionSupported, systemReducedMotion, systemTextScale };
}

export default function FoundationScreen({ onSetup, onOpenCockpit }: { onSetup: () => void; onOpenCockpit: () => void }) {
  const catalog = useForgeCatalog();
  const [vision, setVision] = React.useState('');
  const compose = useLiveCompose(vision);
  const run = useForgeRun();
  const consoleState = useCockpitConsole();
  const now = useNow(run.phase === 'running');
  const platform = usePlatformA11y();
  const [ownerId, setOwnerId] = React.useState<string | null>(null);
  const store = React.useMemo(() => asyncStorageKv(), []);
  const auth = React.useMemo(() => gameforgeAuthPort(), []);
  const load = React.useCallback(() => loadFoundation(store), [store]);
  const save = React.useCallback((snap: PersistSnapshot) => saveFoundation(store, snap), [store]);

  return (
    <FoundationShell
      ports={{
        load,
        save,
        auth,
        platform,
        catalog: {
          beats: catalog.beats,
          beatsLive: catalog.beatsLive,
          eras: catalog.eras,
          generations: catalog.generations,
          loading: catalog.loading,
          error: catalog.error,
          reload: catalog.reload,
        },
        composeSummary: composeSummaryOf(compose.result),
        run: {
          phase: run.phase,
          payload: run.payload,
          error: run.error,
          startedAt: run.startedAt,
          finishedAt: run.finishedAt,
          ownerId,
          onStart: (projectId, req) => { setOwnerId(projectId); void run.start(req); },
          onCancel: run.cancel,
        },
        now,
        console: {
          entries: consoleState.entries.map((entry) => ({ ok: entry.ok, summary: entry.summary })),
          busy: consoleState.busy,
          failures: consoleFailures(consoleState.entries),
          onStatus: () => { void consoleState.submit('STATUS'); },
        },
        onSetup,
        onOpenCockpit,
        onVision: setVision,
      }}
    />
  );
}
