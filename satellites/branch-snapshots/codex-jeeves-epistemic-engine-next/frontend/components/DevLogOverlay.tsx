/**
 * DevLogOverlay — always-on, on-screen boot/diagnostics log.
 *
 *  Renders a floating, collapsible panel on TOP of every route so the live
 *  boot trace (the same [BOOTTRACE] stream that prints to logcat) is visible
 *  ON THE DEVICE without any cable or external tooling. This is the "visual
 *  logs on all pages" the user asked for.
 *
 *  • Subscribes to bootTracer's live pub/sub → updates in real time.
 *  • Collapses to a small floating pill (tap to expand). Expanded view shows
 *    the last ~40 steps with +Xms offsets, newest at the bottom, auto-scroll.
 *  • "Copy" dumps the whole trace to the clipboard. "Safe Mode" jumps to the
 *    recovery screen. "Hide" removes it for the session.
 *  • Mounted once in app/_layout.tsx so it overlays the entire app.
 */
import React, { useEffect, useRef, useState } from 'react';
import {
  View, Text, TouchableOpacity, ScrollView, StyleSheet, Platform,
} from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { subscribeTrace, navToSafeMode, type TraceStep } from '../utils/bootTracer';

const T0 = Date.now();

export default function DevLogOverlay() {
  const [steps, setSteps] = useState<TraceStep[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [hidden, setHidden] = useState(false);
  const [copied, setCopied] = useState(false);
  const scrollRef = useRef<ScrollView | null>(null);

  useEffect(() => {
    const unsub = subscribeTrace((t) => setSteps(t.slice(-60)));
    return unsub;
  }, []);

  useEffect(() => {
    // Auto-scroll to newest line.
    const id = setTimeout(() => { try { scrollRef.current?.scrollToEnd({ animated: false }); } catch {} }, 30);
    return () => clearTimeout(id);
  }, [steps]);

  if (hidden) {
    // Tiny restore dot in the corner so it's never permanently lost.
    return (
      <TouchableOpacity style={styles.restoreDot} onPress={() => setHidden(false)} accessibilityLabel="Show logs">
        <Text style={styles.restoreDotText}>≡</Text>
      </TouchableOpacity>
    );
  }

  const last = steps[steps.length - 1];

  if (!expanded) {
    return (
      <TouchableOpacity style={styles.pill} onPress={() => setExpanded(true)} accessibilityLabel="Expand logs">
        <Text style={styles.pillDot}>●</Text>
        <Text style={styles.pillText} numberOfLines={1}>
          {last ? last.step : 'boot…'} ({steps.length})
        </Text>
      </TouchableOpacity>
    );
  }

  const copyAll = async () => {
    try {
      const text = steps.map(s => `+${s.ts - T0}ms  ${s.step}`).join('\n');
      await Clipboard.setStringAsync(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {}
  };

  return (
    <View style={styles.panel}>
      <View style={styles.bar}>
        <Text style={styles.title}>BOOT LOG · {steps.length}</Text>
        <View style={styles.barBtns}>
          <TouchableOpacity style={styles.btn} onPress={copyAll}>
            <Text style={styles.btnText}>{copied ? 'Copied' : 'Copy'}</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.btn} onPress={() => navToSafeMode('overlay_button')}>
            <Text style={styles.btnText}>Safe Mode</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.btn} onPress={() => setExpanded(false)}>
            <Text style={styles.btnText}>▾</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.btn} onPress={() => setHidden(true)}>
            <Text style={styles.btnText}>✕</Text>
          </TouchableOpacity>
        </View>
      </View>
      <ScrollView ref={scrollRef} style={styles.scroll} contentContainerStyle={styles.scrollInner}>
        {steps.map((s, i) => {
          const danger = /ERROR|REJECTION|fail|crash|NAV_SAFE/i.test(s.step);
          return (
            <Text key={`${s.ts}-${i}`} style={[styles.line, danger && styles.lineDanger]} numberOfLines={2}>
              <Text style={styles.ms}>+{s.ts - T0}ms </Text>{s.step}
            </Text>
          );
        })}
        {steps.length === 0 ? <Text style={styles.line}>waiting for boot steps…</Text> : null}
      </ScrollView>
    </View>
  );
}

const MONO = Platform.select({ ios: 'Menlo', android: 'monospace', default: 'monospace' });

const styles = StyleSheet.create({
  panel: {
    position: 'absolute',
    left: 6, right: 6, bottom: 6,
    maxHeight: 230,
    pointerEvents: 'box-none',
    backgroundColor: 'rgba(6,10,20,0.92)',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#3b2a6b',
    overflow: 'hidden',
    zIndex: 99999,
    elevation: 99999,
  },
  bar: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 10, paddingVertical: 6,
    backgroundColor: 'rgba(124,58,237,0.22)',
    borderBottomWidth: 1, borderBottomColor: '#3b2a6b',
  },
  title: { color: '#c4b5fd', fontSize: 11, fontWeight: '900', letterSpacing: 1 },
  barBtns: { flexDirection: 'row', gap: 6 },
  btn: {
    backgroundColor: 'rgba(167,139,250,0.18)',
    paddingHorizontal: 9, paddingVertical: 4, borderRadius: 6,
    minWidth: 30, alignItems: 'center',
  },
  btnText: { color: '#e9d5ff', fontSize: 11, fontWeight: '800' },
  scroll: { maxHeight: 190 },
  scrollInner: { padding: 8 },
  line: { color: '#cbd5e1', fontSize: 10, lineHeight: 14, fontFamily: MONO },
  lineDanger: { color: '#fca5a5', fontWeight: '700' },
  ms: { color: '#7c8aa0' },
  pill: {
    position: 'absolute', left: 6, bottom: 6,
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: 'rgba(6,10,20,0.92)',
    borderWidth: 1, borderColor: '#3b2a6b',
    paddingHorizontal: 10, paddingVertical: 6, borderRadius: 20,
    maxWidth: '70%', zIndex: 99999, elevation: 99999,
  },
  pillDot: { color: '#34d399', fontSize: 10 },
  pillText: { color: '#cbd5e1', fontSize: 11, fontFamily: MONO },
  restoreDot: {
    position: 'absolute', left: 6, bottom: 6,
    width: 34, height: 34, borderRadius: 17,
    backgroundColor: 'rgba(6,10,20,0.9)',
    borderWidth: 1, borderColor: '#3b2a6b',
    alignItems: 'center', justifyContent: 'center',
    zIndex: 99999, elevation: 99999,
  },
  restoreDotText: { color: '#c4b5fd', fontSize: 16, fontWeight: '900' },
});
