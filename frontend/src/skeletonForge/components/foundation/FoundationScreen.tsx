/**
 * Live studio screen. Project builds go through useForgeRun, and cockpit
 * STATUS goes through useCockpitConsole — the same owners as the forge
 * cockpit, not a second poller.
 */
import React from 'react';
import * as Crypto from 'expo-crypto';
import { getAuthEpoch, subscribeAuthChanges } from '../../../auth/gameforgeAuth';
import { shareGodotSourceArchive } from '../../shareSourceArchive';
import type { RunRequest } from '../../types';
import { AccessibilityInfo, PixelRatio, Platform } from 'react-native';
import { gameforgeAuthPort } from '../../foundation/authPort';
import type { A11yPlatformSnapshot } from '../../foundation/a11y';
import {
  reconcileStudioReturn, recoverStudioReturnAsCopy,
  type PersistSnapshot, type StudioProject,
} from '../../foundation/model';
import { handoffFromStudio, studioStateFromHandoff } from '../../creatorBridge';
import { storeCreatorBridge, withCreatorBridge } from '../../creatorBridgeStorage';
import { asyncStorageKv, hasLegacyStudioProjects, legacyReadOnlyKv } from '../../foundation/storageDevice';
import { loadFoundation, saveFoundation, updateFoundation } from '../../foundation/storage';
import { composeSummaryOf, consoleFailures } from '../../cockpitScreen';
import { useCockpitConsole } from '../../consoleHooks';
import { useForgeCatalog, useForgeRun, useLiveCompose, useNow } from '../../hooks';
import { useReduceMotion } from '../../../hooks/useReduceMotion';
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

export default function FoundationScreen(props: { onSetup: () => void; onOpenCockpit: () => void }) {
  const [authEpoch, setAuthEpoch] = React.useState(() => getAuthEpoch());
  React.useEffect(() => subscribeAuthChanges(() => setAuthEpoch(getAuthEpoch())), []);
  // The entire session, not merely its project list, must be discarded on
  // account rotation. Compose results, console history, source artifacts,
  // the owner ID and any in-flight run all belong to the previous identity.
  return <FoundationScreenSession key={authEpoch} sessionEpoch={authEpoch} {...props} />;
}

function FoundationScreenSession({ onSetup, onOpenCockpit, sessionEpoch }: {
  onSetup: () => void; onOpenCockpit: () => void; sessionEpoch: number;
}) {
  const catalog = useForgeCatalog();
  const [vision, setVision] = React.useState('');
  const compose = useLiveCompose(vision);
  const run = useForgeRun();
  const consoleState = useCockpitConsole();
  const now = useNow(run.phase === 'running');
  const platform = usePlatformA11y();
  const [ownerId, setOwnerId] = React.useState<string | null>(null);
  const [legacyAvailable, setLegacyAvailable] = React.useState(false);
  const [studioReturnNotice, setStudioReturnNotice] = React.useState<string | null>(null);
  const [cockpitTransferError, setCockpitTransferError] = React.useState<string | null>(null);
  const cockpitTransferLock = React.useRef(false);
  const runOwnerEpoch = React.useRef<number | null>(null);
  const runGeneration = React.useRef(0);
  const exportLock = React.useRef(false);
  const [exportBusy, setExportBusy] = React.useState(false);
  const [exportError, setExportError] = React.useState<string | null>(null);
  React.useEffect(() => {
    let mounted = true;
    setLegacyAvailable(false);
    void hasLegacyStudioProjects().then((present) => {
      if (mounted) setLegacyAvailable(present);
    }).catch(() => { if (mounted) setLegacyAvailable(false); });
    return () => { mounted = false; };
  }, []);
  const startForge = React.useCallback((projectId: string, request: RunRequest) => {
    runOwnerEpoch.current = getAuthEpoch();
    runGeneration.current += 1;
    setOwnerId(projectId);
    setExportError(null);
    void run.start(request);
  }, [run.start]);
  const exportGodot = React.useCallback(() => {
    if (exportLock.current || !ownerId || run.phase !== 'done'
      || run.payload?.succeeded !== true || run.payload.source_export?.status !== 'ready') return;
    const epoch = runOwnerEpoch.current;
    const generation = runGeneration.current;
    if (epoch === null || epoch !== getAuthEpoch()) {
      setExportError('Account changed since this game was generated; forge again before exporting.');
      return;
    }
    exportLock.current = true;
    setExportBusy(true);
    setExportError(null);
    void shareGodotSourceArchive(run.payload, () =>
      epoch === getAuthEpoch() && generation === runGeneration.current
    ).catch((error: unknown) => {
      const message = error instanceof Error ? error.message : '';
      setExportError(message.startsWith('Godot') || message.startsWith('Device') || message.startsWith('Source')
        ? message.slice(0, 180)
        : 'The source ZIP could not be shared on this device.');
    }).finally(() => {
      exportLock.current = false;
      setExportBusy(false);
    });
  }, [ownerId, run.phase, run.payload]);
  const store = React.useMemo(() => asyncStorageKv(sessionEpoch), [sessionEpoch]);
  const auth = React.useMemo(() => gameforgeAuthPort(), []);
  const load = React.useCallback(async () => {
    const epoch = sessionEpoch;
    if (getAuthEpoch() !== epoch) throw new Error('Stale Studio session');
    const result = await loadFoundation(store);
    if (result.holdSaves) return result;
    if (epoch !== getAuthEpoch()) throw new Error('Account changed while loading Studio projects');
    // Consume only after the complete receiving-project save. A failed
    // write keeps the original envelope for the original account, rather
    // than trying to reissue private data into the next session's scope.
    const transferred = await withCreatorBridge('studio', async (returned) => {
      const restored = studioStateFromHandoff(returned);
      if (!restored || !returned.studioProjectId || !returned.studioProjectUpdatedAt) {
        throw new Error('Returned Forge draft is not source-bound to a Studio project');
      }
      if (epoch !== getAuthEpoch()) throw new Error('Account changed while applying Studio return');
      const receipt = await Crypto.digestStringAsync(
        Crypto.CryptoDigestAlgorithm.SHA256, 'skeleton.studio.return.v1:' + JSON.stringify(returned),
      );
      if (epoch !== getAuthEpoch()) throw new Error('Account changed while binding Studio return');
      const sourceId = returned.studioProjectId;
      const sourceRevision = returned.studioProjectUpdatedAt;
      const committed = await updateFoundation(store, current => {
        if (epoch !== getAuthEpoch()) throw new Error('Account changed before Studio return publication');
        const at = new Date().toISOString();
        const reconciled = reconcileStudioReturn(
          current.projects, sourceId, sourceRevision, restored, at, receipt,
        );
        if (reconciled.status === 'invalid') throw new Error('Returned Forge draft failed project admission');
        const originalUpdated = reconciled.status === 'applied' || reconciled.status === 'already-applied';
        const projects = originalUpdated ? reconciled.projects
          : recoverStudioReturnAsCopy(current.projects, restored, at, receipt).projects;
        const snapshot = { ...current, projects };
        return { snapshot, result: { loaded: snapshot, originalUpdated } };
      });
      if (epoch !== getAuthEpoch()) throw new Error('Account changed while committing Studio return');
      setStudioReturnNotice(committed.originalUpdated
        ? 'Advanced Forge edits were saved to the original Studio project.'
        : 'The original project changed or was deleted. Your Forge edits were preserved as a separate project copy.');
      return committed.loaded;
    });
    if (epoch !== getAuthEpoch()) throw new Error('Account changed before publishing Studio projects');
    // A no-handoff path may have waited for another adapter; reload under
    // the namespace queue rather than exposing a stale initial observation.
    return transferred ?? await loadFoundation(store);
  }, [store, sessionEpoch]);
  const save = React.useCallback((snap: PersistSnapshot) => saveFoundation(store, snap), [store]);
  const openAdvancedCockpit = React.useCallback((project?: StudioProject, snapshot?: PersistSnapshot) => {
    if (cockpitTransferLock.current || sessionEpoch !== getAuthEpoch()) return;
    if (!project) { onOpenCockpit(); return; }
    if (!snapshot || snapshot.holdSaves || snapshot.projectsCorrupt
        || !snapshot.projects.some(item => item.id === project.id && item.updatedAt === project.updatedAt)) {
      setCockpitTransferError('Save and verify the source project before opening Forge cockpit.');
      return;
    }
    cockpitTransferLock.current = true;
    setCockpitTransferError(null);
    const epoch = getAuthEpoch();
    try {
      const envelope = handoffFromStudio(project.questionnaire, project.id, project.updatedAt);
      // Persist the exact source revision before publishing its handoff.
      void saveFoundation(store, snapshot).then(() => {
        if (epoch !== getAuthEpoch()) throw new Error('Account changed before Forge transfer');
        return storeCreatorBridge(envelope, epoch);
      }).then(() => {
        if (epoch !== getAuthEpoch()) throw new Error('Account changed during Forge transfer');
        onOpenCockpit();
      }).catch(() => {
        setCockpitTransferError('Could not preserve this project for Forge cockpit. Navigation cancelled.');
      }).finally(() => { cockpitTransferLock.current = false; });
    } catch {
      cockpitTransferLock.current = false;
      setCockpitTransferError('This Studio project could not be transferred into Forge cockpit.');
    }
  }, [onOpenCockpit, sessionEpoch, store]);
  const importLegacy = React.useCallback(async () => {
    const epoch = getAuthEpoch();
    const old = await loadFoundation(legacyReadOnlyKv());
    if (epoch !== getAuthEpoch()) throw new Error('Account changed before legacy import completed');
    if (old.projectsCorrupt) throw new Error('Legacy projects could not be verified; the original data was left unchanged.');
    setLegacyAvailable(false);
    return old.projects;
  }, []);

  return (
    <FoundationShell
      ports={{
        legacyAvailable,
        importLegacy,
        studioReturnNotice,
        cockpitTransferError,
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
          request: run.request,
          onStart: startForge,
          onCancel: run.cancel,
          onExport: exportGodot,
          exportBusy,
          exportError,
        },
        now,
        console: {
          entries: consoleState.entries.map((entry) => ({ ok: entry.ok, summary: entry.summary })),
          busy: consoleState.busy,
          failures: consoleFailures(consoleState.entries),
          onStatus: () => { void consoleState.submit('STATUS'); },
        },
        onSetup,
        onOpenCockpit: openAdvancedCockpit,
        onVision: setVision,
      }}
    />
  );
}
