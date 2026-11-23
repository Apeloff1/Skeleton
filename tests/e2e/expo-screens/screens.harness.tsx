/**
 * Screen harness: renders one reviewed Expo route (?screen=<route>) with
 * react-native-web so browser journeys and axe can inspect it in isolation.
 * expo-router is replaced by ./expo-router.stub; network calls go to the
 * same-origin host, which answers /api/* with whatever the journey stubs.
 */
import React from 'react';
import { AppRegistry, Text, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
// eslint-disable-next-line import/no-unresolved
import { SCREENS } from 'virtual:screens';

class Boundary extends React.Component<{ children: React.ReactNode }, { error: string | null }> {
  state = { error: null as string | null };
  static getDerivedStateFromError(error: unknown) { return { error: String((error as Error)?.message ?? error) }; }
  render() {
    if (this.state.error) return <View testID="harness-crash"><Text>{`Harness crash: ${this.state.error}`}</Text></View>;
    return this.props.children;
  }
}

function Host() {
  const name = new URLSearchParams(location.search).get('screen') ?? '';
  const [Screen, setScreen] = React.useState<React.ComponentType | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  React.useEffect(() => {
    const load = (SCREENS as Record<string, () => Promise<{ default: React.ComponentType }>>)[name];
    if (!load) { setError(`unknown screen ${name}`); return; }
    load().then((m) => setScreen(() => m.default)).catch((e: unknown) => setError(String((e as Error)?.message ?? e)));
  }, [name]);
  if (error) return <Text testID="harness-error">{error}</Text>;
  if (!Screen) return <Text testID="harness-loading">Loading screen…</Text>;
  return <SafeAreaProvider><Boundary><Screen /></Boundary></SafeAreaProvider>;
}

AppRegistry.registerComponent('ScreenHarness', () => Host);
AppRegistry.runApplication('ScreenHarness', { rootTag: document.getElementById('root') });
