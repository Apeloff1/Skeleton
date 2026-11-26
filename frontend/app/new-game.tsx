/**
 * /new-game — prompt → live build → result, through the backend forge gateway.
 *
 * The gateway authenticates the signed-in user and seals the engine request
 * server-side (`POST /api/forge-gateway/game/build`), so this screen never
 * handles an engine seal. `?build=<execution_id>` resumes tracking after a
 * reload or when opened from a notification.
 */
import React from 'react';
import { ScrollView, StyleSheet } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';

import { withScreenGuard } from '../src/components/withScreenGuard';
import { Screen } from '../src/components/primitives';
import { NewGameView, briefError } from '../src/forgeGateway/NewGameView';
import { getGatewayStatus } from '../src/forgeGateway/client';
import type { Playtest } from '../src/forgeGateway/model';
import { useGameBuild } from '../src/forgeGateway/useGameBuild';

function NewGameRoute() {
  const router = useRouter();
  const params = useLocalSearchParams<{ build?: string; brief?: string }>();
  const resumeId = typeof params.build === 'string' && params.build ? params.build : null;
  const [brief, setBrief] = React.useState(typeof params.brief === 'string' ? params.brief.slice(0, 4000) : '');
  const [playtest, setPlaytest] = React.useState<Playtest>('auto');
  const [validationError, setValidationError] = React.useState<string | null>(null);
  const [unavailable, setUnavailable] = React.useState<string | null>(null);
  const { state, start, reset } = useGameBuild(resumeId);

  React.useEffect(() => {
    const ctl = new AbortController();
    void getGatewayStatus(ctl.signal).then((res) => {
      if (ctl.signal.aborted) return;
      if (res.ok && res.data && (!res.data.engine_configured || !res.data.seal_configured)) {
        setUnavailable('Game building is not configured on this server yet. An administrator needs to connect the Skeleton engine.');
      } else if (res.status === 401) {
        setUnavailable('Sign in to build games.');
      }
    });
    return () => ctl.abort();
  }, []);

  const submit = React.useCallback(async () => {
    const problem = briefError(brief);
    setValidationError(problem);
    if (problem) return;
    const executionId = await start(brief, playtest);
    if (executionId) {
      try { router.setParams({ build: executionId }); } catch { /* params are a convenience */ }
    }
  }, [brief, playtest, start, router]);

  const again = React.useCallback(() => {
    reset();
    try { router.setParams({ build: '' }); } catch { /* ignore */ }
  }, [reset, router]);

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <NewGameView
          state={state}
          brief={brief}
          playtest={playtest}
          validationError={validationError}
          unavailableReason={unavailable}
          onBriefChange={(value) => { setBrief(value); if (validationError) setValidationError(null); }}
          onPlaytestChange={setPlaytest}
          onSubmit={() => { void submit(); }}
          onReset={again}
          onOpenBuilds={() => router.push('/my-builds')}
        />
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { padding: 20, maxWidth: 760, width: '100%', alignSelf: 'center' },
});

NewGameRoute.displayName = 'NewGameRoute';

export default withScreenGuard(NewGameRoute, 'NewGameRoute');
