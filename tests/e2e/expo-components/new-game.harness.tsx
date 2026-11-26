/**
 * Browser harness for the /new-game flow: the real NewGameView, useGameBuild
 * hook, gateway client and apiClient transport, rendered with
 * react-native-web against a live backend gateway + engine. It mirrors
 * app/new-game.tsx without the expo-router/Screen chrome, which needs the full
 * Metro bundle.
 */
import React from 'react';
import { AppRegistry, ScrollView } from 'react-native';
import { NewGameView, briefError } from '../../../frontend/src/forgeGateway/NewGameView';
import { getGatewayStatus } from '../../../frontend/src/forgeGateway/client';
import { useGameBuild } from '../../../frontend/src/forgeGateway/useGameBuild';
import type { Playtest } from '../../../frontend/src/forgeGateway/model';
import { color } from '../../../frontend/src/foundation/tokens';

function NewGameHarness() {
  const [brief, setBrief] = React.useState('');
  const [playtest, setPlaytest] = React.useState<Playtest>('auto');
  const [validationError, setValidationError] = React.useState<string | null>(null);
  const [unavailable, setUnavailable] = React.useState<string | null>(null);
  const { state, start, reset } = useGameBuild(new URLSearchParams(location.search).get('build'));
  React.useEffect(() => {
    void getGatewayStatus().then((res) => {
      if (res.ok && res.data && (!res.data.engine_configured || !res.data.seal_configured)) {
        setUnavailable('Game building is not configured on this server yet. An administrator needs to connect the Skeleton engine.');
      } else if (res.status === 401) setUnavailable('Sign in to build games.');
    });
  }, []);
  return (
    <ScrollView style={{ backgroundColor: color.bg }} contentContainerStyle={{ padding: 20, maxWidth: 760, width: '100%', alignSelf: 'center' }}>
      <main>
        <NewGameView
          state={state} brief={brief} playtest={playtest} validationError={validationError} unavailableReason={unavailable}
          onBriefChange={(v) => { setBrief(v); setValidationError(null); }}
          onPlaytestChange={setPlaytest}
          onSubmit={() => { const p = briefError(brief); setValidationError(p); if (!p) void start(brief, playtest); }}
          onReset={reset}
          onOpenBuilds={() => { location.hash = '#/my-builds'; }}
        />
      </main>
    </ScrollView>
  );
}

AppRegistry.registerComponent('NewGameHarness', () => NewGameHarness);
AppRegistry.runApplication('NewGameHarness', { rootTag: document.getElementById('root') });
