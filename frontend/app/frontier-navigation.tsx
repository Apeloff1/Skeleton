/** Opt-in browser GPS inspector for the game-frontier navigation studio.
 *
 * No precise location leaves this component; survey projects receive only
 * deliberate operator-provided benchmark observations through Jeeves.
 */
import React from 'react';
import {
  SafeAreaView, ScrollView, View, Text,
  TouchableOpacity, StyleSheet, Platform,
} from 'react-native';
import {
  startForegroundGPS, type FrontierGPSSession, type FrontierPositionFix,
} from '../src/product/frontierLiveGPS';

export default function FrontierNavigation() {
  const session = React.useRef<FrontierGPSSession | null>(null);
  const [position, setPosition] = React.useState<FrontierPositionFix | null>(null);
  const [status, setStatus] = React.useState('Not collecting device position');
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => () => { session.current?.stop(); session.current = null; }, []);

  const stop = React.useCallback(() => {
    session.current?.stop();
    session.current = null;
    setPosition(null);
    setStatus('GPS stopped; session coordinates cleared');
  }, []);

  const start = React.useCallback(async () => {
    if (busy || session.current) return;
    setBusy(true);
    setStatus('Requesting foreground permission from this device');
    try {
      const handle = await startForegroundGPS({
        userInitiated: true,
        onFix: reading => {
          setPosition(reading);
          setStatus('Live device GPS — foreground session only');
        },
        onError: error => setStatus(error.message),
        maxAccuracyM: 75,
        maxAgeMs: 10000,
      });
      session.current = handle;
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Location denied');
    } finally {
      setBusy(false);
    }
  }, [busy]);

  return (
    <SafeAreaView style={styles.root}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.heading}>Jeeves Frontier Navigation</Text>
        <Text style={styles.subhead}>Live GPS and surveyed controls</Text>
        <Text style={styles.explain}>
          Foreground GPS is optional. The app requests device location only
          after you press Start. Measurements remain in this view; stopping
          clears the precise coordinates. Nothing is sent to Jeeves
          automatically.
        </Text>
        <Text style={styles.status}>{status}</Text>
        {Platform.OS !== 'web' &&
          <Text style={styles.warning}>
            Native GPS requires the approved Expo foreground-location
            adapter in the built app. It is not active in this preview.
          </Text>}
        <View style={styles.buttons}>
          <TouchableOpacity
            accessibilityRole="button" disabled={busy || session.current !== null}
            onPress={start} style={styles.start}>
            <Text style={styles.label}>Start foreground GPS</Text>
          </TouchableOpacity>
          <TouchableOpacity accessibilityRole="button"
            onPress={stop} style={styles.stop}>
            <Text style={styles.label}>Stop and clear</Text>
          </TouchableOpacity>
        </View>
        {position &&
          <View style={styles.readout}>
            <Text style={styles.row}>Latitude: {position.latitude_deg.toFixed(7)}°</Text>
            <Text style={styles.row}>Longitude: {position.longitude_deg.toFixed(7)}°</Text>
            <Text style={styles.row}>
              Height: {position.altitude_m === null
                ? 'unavailable' : position.altitude_m.toFixed(1) + ' m'}
            </Text>
            <Text style={styles.row}>
              Horizontal uncertainty: ±{position.horizontal_accuracy_m.toFixed(1)} m
            </Text>
            <Text style={styles.row}>
              Device time: {new Date(position.timestamp_ms).toLocaleTimeString()}
            </Text>
          </View>}
        <Text style={styles.explain}>
          Surveyed positions require known, independently verified WGS84
          control-point coordinates and true bearings. The game-frontier
          survey engine compares those observations with GPS separately and
          reports uncertainty; it does not certify a legal boundary.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: {flex: 1, backgroundColor: '#0c1422'},
  content: {padding: 22, gap: 14},
  heading: {color: '#e8f0ff', fontSize: 26, fontWeight: 'bold'},
  subhead: {color: '#9fc7fb', fontSize: 18, fontWeight: '600'},
  explain: {color: '#c0cce0', lineHeight: 22, fontSize: 14},
  status: {color: '#f9c874', fontWeight: '600'},
  warning: {color: '#ffc98f', lineHeight: 20},
  buttons: {flexDirection: 'row', gap: 10, flexWrap: 'wrap'},
  start: {backgroundColor: '#2563eb', borderRadius: 9, padding: 12},
  stop: {backgroundColor: '#6b2d34', borderRadius: 9, padding: 12},
  label: {color: '#fff', fontWeight: 'bold'},
  readout: {backgroundColor: '#18263f', padding: 18, borderRadius: 12, gap: 8},
  row: {color: '#d5e6ff', fontSize: 16},
});
