/**
 * MLConfigPanel
 * -------------------------------------------------------------------
 * Live ML-config tuning UI for the Done state of GalaxyStudioFactoryModal.
 * Fetches the validation schema from GET /api/galaxy-studio/ml-config/schema
 * and renders the 13 ML dials (Cross-Entropy, Fine-Tuning, In-Context Log-Probs)
 * as native sliders / pickers / toggles with proper ranges.
 *
 * On submit it POSTs to /build/{build_id}/ml-config and surfaces any
 * server-side rejections inline.
 */
import { NATIVE_DRIVER } from '../../src/utils/platformStyles';
import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator,
  Animated, Platform, StyleSheet,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import Slider from '@react-native-community/slider';
import { Ionicons } from '@expo/vector-icons';
import { T } from './GalaxyStudioFactoryModal.styles';

// ─── Local styles (inline since this is a self-contained sub-screen) ──

// Backend base URL — mirrors the modal's BACKEND constant pattern
const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

// 2026-05-15 — Schema cache: AsyncStorage key + TTL (24h). Schema changes are rare,
// so we serve cached values immediately and revalidate in the background.
const SCHEMA_CACHE_KEY = '@galaxy_studio:ml_config_schema:v1';
const SCHEMA_CACHE_TTL_MS = 24 * 60 * 60 * 1000;

// Friendly labels + groups for the 13 keys
const KEY_LABEL: Record<string, string> = {
  ce_loss_weight:      'CE Loss Weight',
  ce_temperature:      'CE Temperature',
  label_smoothing:     'Label Smoothing',
  focal_gamma:         'Focal Loss γ',
  loss_type:           'Loss Type',
  preference_finetune: 'Preference Finetune',
  lora_r:              'LoRA Rank',
  qlora_4bit:          'QLoRA 4-bit',
  fine_tune_mode:      'Fine-Tune Mode',
  icl_logprobs_depth:  'ICL Log-Probs Depth',
  icl_samples:         'ICL Samples',
  self_consistency_k:  'Self-Consistency k',
  mcts_depth:          'MCTS Depth',
};

const KEY_GROUP: Record<string, string> = {
  ce_loss_weight:      'Cross-Entropy',
  ce_temperature:      'Cross-Entropy',
  label_smoothing:     'Cross-Entropy',
  focal_gamma:         'Cross-Entropy',
  loss_type:           'Cross-Entropy',
  preference_finetune: 'Fine-Tuning',
  lora_r:              'Fine-Tuning',
  qlora_4bit:          'Fine-Tuning',
  fine_tune_mode:      'Fine-Tuning',
  icl_logprobs_depth:  'In-Context Learning',
  icl_samples:         'In-Context Learning',
  self_consistency_k:  'In-Context Learning',
  mcts_depth:          'In-Context Learning',
};

const GROUP_ORDER = ['Cross-Entropy', 'Fine-Tuning', 'In-Context Learning'];

interface SchemaEntry {
  type: 'int' | 'float' | 'bool' | 'enum' | 'int_set' | 'list[str]';
  min?: number;
  max?: number;
  values?: number[];
  vocab?: string[];
}
type Schema = Record<string, SchemaEntry>;

interface MLConfigPanelProps {
  buildId: string;
  onClose: () => void;
}

export const MLConfigPanel: React.FC<MLConfigPanelProps> = ({ buildId, onClose }) => {
  const [schema, setSchema] = useState<Schema | null>(null);
  const [current, setCurrent] = useState<Record<string, any>>({});
  const [draft, setDraft] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedFlash, setSavedFlash] = useState('');
  const [rejected, setRejected] = useState<Record<string, string>>({});
  // 2026-05-15 — Reset diff preview + cache age display
  const [resetDiff, setResetDiff] = useState<{ key: string; from: any; to: any }[] | null>(null);
  const [cacheTs, setCacheTs] = useState<number | null>(null);
  const [revalidating, setRevalidating] = useState(false);

  // ─── Initial fetch: schema (with AsyncStorage cache) + current ml_config ──
  useEffect(() => {
    let cancelled = false;
    (async () => {
      // 1) Try to hydrate from cache first for instant render
      try {
        const cached = await AsyncStorage.getItem(SCHEMA_CACHE_KEY);
        if (cached && !cancelled) {
          const parsed = JSON.parse(cached);
          if (parsed?.schema && parsed?.ts && Date.now() - parsed.ts < SCHEMA_CACHE_TTL_MS) {
            setSchema(parsed.schema as Schema);
            setCacheTs(parsed.ts);
            setLoading(false);  // unblock UI immediately
          }
        }
      } catch (e) {
        // cache read failure is non-fatal
        console.warn('schema cache hydrate failed:', e);
      }

      // 2) Always revalidate from backend in background
      setRevalidating(true);
      try {
        const [schRes, mlRes] = await Promise.all([
          fetch(`${BACKEND}/api/galaxy-studio/ml-config/schema`),
          fetch(`${BACKEND}/api/galaxy-studio/build/${buildId}/ml-config`),
        ]);
        const sch = await schRes.json();
        const ml  = await mlRes.json();
        if (cancelled) return;
        setSchema(sch as Schema);
        setCurrent((ml.ml_config || {}) as Record<string, any>);
        setDraft({});
        // 3) Refresh cache (best-effort)
        const freshTs = Date.now();
        try {
          await AsyncStorage.setItem(
            SCHEMA_CACHE_KEY,
            JSON.stringify({ schema: sch, ts: freshTs })
          );
          setCacheTs(freshTs);
        } catch { /* ignore */ }
      } catch (e) {
        console.warn('MLConfigPanel fetch failed:', e);
      } finally {
        if (!cancelled) {
          setLoading(false);
          setRevalidating(false);
        }
      }
    })();
    return () => { cancelled = true; };
  }, [buildId]);

  // ─── Helpers ────────────────────────────────────────────────────
  // Build a default-values map from the schema for the Reset action.
  const defaultsFromSchema = useCallback((sch: Schema | null): Record<string, any> => {
    if (!sch) return {};
    const out: Record<string, any> = {};
    Object.entries(sch).forEach(([k, spec]) => {
      if (spec.type === 'bool')          out[k] = false;
      else if (spec.type === 'int_set')  out[k] = spec.values?.[0] ?? null;
      else if (spec.type === 'enum')     out[k] = spec.vocab?.[0] ?? '';
      else if (spec.type === 'list[str]') out[k] = [];
      else if (spec.type === 'int')      out[k] = Math.round((spec.min ?? 0));
      else if (spec.type === 'float')    out[k] = Number((spec.min ?? 0).toFixed(2));
    });
    return out;
  }, []);

  const handleReset = useCallback(() => {
    if (!schema) return;
    // 2026-05-15 — Open a diff preview rather than staging silently.
    const defaults = defaultsFromSchema(schema);
    const diff: { key: string; from: any; to: any }[] = [];
    Object.entries(defaults).forEach(([k, defVal]) => {
      const curVal = (k in draft) ? draft[k] : (k in current ? current[k] : undefined);
      const same =
        Array.isArray(curVal) && Array.isArray(defVal)
          ? curVal.length === defVal.length && curVal.every((v, i) => v === defVal[i])
          : curVal === defVal;
      if (!same) diff.push({ key: k, from: curVal, to: defVal });
    });
    if (!diff.length) {
      setSavedFlash('Already at defaults — nothing to reset.');
      setTimeout(() => setSavedFlash(''), 3500);
      return;
    }
    setResetDiff(diff);
  }, [schema, defaultsFromSchema, draft, current]);

  // 2026-05-15 — Per-dial single reset (no confirmation modal — single dial is reversible)
  const resetSingleDial = useCallback((key: string) => {
    if (!schema || !(key in schema)) return;
    const defaults = defaultsFromSchema(schema);
    const defVal = defaults[key];
    const curVal = (key in draft) ? draft[key] : (key in current ? current[key] : undefined);
    const same =
      Array.isArray(curVal) && Array.isArray(defVal)
        ? curVal.length === defVal.length && curVal.every((v, i) => v === defVal[i])
        : curVal === defVal;
    if (same) return;
    setDraft(prev => ({ ...prev, [key]: defVal }));
    setRejected(prev => {
      if (!(key in prev)) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
  }, [schema, defaultsFromSchema, draft, current]);

  // 2026-05-15 — Helper: is the given dial currently at its default value?
  const isAtDefault = useCallback((key: string): boolean => {
    if (!schema || !(key in schema)) return true;
    const defaults = defaultsFromSchema(schema);
    const defVal = defaults[key];
    const curVal = (key in draft) ? draft[key] : (key in current ? current[key] : undefined);
    return Array.isArray(curVal) && Array.isArray(defVal)
      ? curVal.length === defVal.length && curVal.every((v, i) => v === defVal[i])
      : curVal === defVal;
  }, [schema, defaultsFromSchema, draft, current]);

  const confirmReset = useCallback(() => {
    if (!schema || !resetDiff) return;
    const defaults = defaultsFromSchema(schema);
    // Only stage the dials that actually changed (saves bandwidth)
    const onlyChanged: Record<string, any> = {};
    resetDiff.forEach(({ key }) => { onlyChanged[key] = defaults[key]; });
    setDraft(onlyChanged);
    setRejected({});
    setResetDiff(null);
    setSavedFlash(`${resetDiff.length} dial${resetDiff.length > 1 ? 's' : ''} staged for reset — tap Save to apply.`);
    setTimeout(() => setSavedFlash(''), 3500);
  }, [schema, defaultsFromSchema, resetDiff]);

  const valueOf = (key: string): any => {
    if (key in draft) return draft[key];
    if (key in current) return current[key];
    // Sensible defaults when neither draft nor current has it
    const spec = schema?.[key];
    if (!spec) return undefined;
    if (spec.type === 'bool')     return false;
    if (spec.type === 'int_set')  return spec.values?.[0];
    if (spec.type === 'enum')     return spec.vocab?.[0];
    if (spec.type === 'list[str]') return [];
    if (spec.type === 'int' || spec.type === 'float') return spec.min ?? 0;
    return undefined;
  };

  const setKey = (key: string, v: any) => {
    setDraft(prev => ({ ...prev, [key]: v }));
  };

  const handleSave = useCallback(async () => {
    if (!Object.keys(draft).length) return;
    setSaving(true);
    setRejected({});
    try {
      const r = await fetch(`${BACKEND}/api/galaxy-studio/build/${buildId}/ml-config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(draft),
      });
      const out = await r.json();
      if (out.ml_config) setCurrent(out.ml_config);
      if (out.rejected && Object.keys(out.rejected).length) {
        setRejected(out.rejected);
      }
      const numUpdated = Object.keys(out.updated || {}).length;
      const numRejected = Object.keys(out.rejected || {}).length;
      setSavedFlash(numUpdated > 0
        ? `Saved ${numUpdated} dial${numUpdated > 1 ? 's' : ''}${numRejected ? `  ·  ${numRejected} rejected` : ''}`
        : `${numRejected} rejected — see below`);
      // Clear draft for keys that successfully saved
      if (numUpdated > 0) {
        setDraft(prev => {
          const next = { ...prev };
          Object.keys(out.updated || {}).forEach(k => delete next[k]);
          return next;
        });
      }
      setTimeout(() => setSavedFlash(''), 3500);
    } catch (e: any) {
      setSavedFlash(`Error: ${String(e?.message || e).slice(0, 80)}`);
      setTimeout(() => setSavedFlash(''), 3500);
    } finally {
      setSaving(false);
    }
  }, [draft, buildId]);

  // 2026-05-15 — Animated per-dial reset icon (fades + scales in/out)
  const DialResetIcon: React.FC<{ visible: boolean; onPress: () => void; label: string }> = ({ visible, onPress, label }) => {
    const opacity = useRef(new Animated.Value(visible ? 1 : 0)).current;
    const scale   = useRef(new Animated.Value(visible ? 1 : 0.6)).current;
    useEffect(() => {
      Animated.parallel([
        Animated.timing(opacity, { toValue: visible ? 1 : 0, duration: 180, useNativeDriver: NATIVE_DRIVER }),
        Animated.spring(scale,   { toValue: visible ? 1 : 0.6, useNativeDriver: NATIVE_DRIVER, friction: 6, tension: 90 }),
      ]).start();
    }, [visible, opacity, scale]);
    return (
      <Animated.View
        style={{ opacity, transform: [{ scale }], pointerEvents: visible ? 'auto' : 'none' }}
      >
        <TouchableOpacity
          onPress={onPress}
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          accessibilityLabel={`Reset ${label}`}
          accessibilityRole="button"
          disabled={!visible}
        >
          <Ionicons name="refresh-circle-outline" size={16} color={T.textMuted} />
        </TouchableOpacity>
      </Animated.View>
    );
  };

  // 2026-05-15 — Shared row header with per-dial reset affordance
  const RowHeader: React.FC<{ k: string; valueDisplay: React.ReactNode }> = ({ k, valueDisplay }) => {
    const dirty = k in draft;
    const atDef = isAtDefault(k);
    return (
      <View style={kRowHead}>
        <Text style={[kLabel, dirty && { color: T.accent }]}>{KEY_LABEL[k] || k}</Text>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          {valueDisplay}
          <DialResetIcon
            visible={!atDef}
            onPress={() => resetSingleDial(k)}
            label={KEY_LABEL[k] || k}
          />
        </View>
      </View>
    );
  };

  // 2026-05-15 — Cmd/Ctrl+S keyboard shortcut to save (web only)
  useEffect(() => {
    if (Platform.OS !== 'web') return;
    const onKeyDown = (e: any) => {
      const isSave = (e.metaKey || e.ctrlKey) && (e.key === 's' || e.key === 'S');
      if (!isSave) return;
      e.preventDefault();
      // Only fire if we have a draft and aren't already saving
      if (Object.keys(draft).length && !saving) {
        handleSave();
      }
    };
    // @ts-ignore — document only exists on web
    document.addEventListener('keydown', onKeyDown);
    return () => {
      // @ts-ignore
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [draft, saving, handleSave]);

  // ─── Render helpers per control type ───────────────────────────
  const renderControl = (key: string, spec: SchemaEntry) => {
    const v = valueOf(key);
    const rejReason = rejected[key];

    if (spec.type === 'int' || spec.type === 'float') {
      const isInt = spec.type === 'int';
      const step  = isInt ? 1 : (spec.max && spec.max <= 1 ? 0.005 : spec.max && spec.max <= 5 ? 0.05 : 0.1);
      const numV  = typeof v === 'number' ? v : (spec.min ?? 0);
      return (
        <View>
          <RowHeader k={key} valueDisplay={<Text style={kVal}>{isInt ? Math.round(numV) : Number(numV).toFixed(2)}</Text>} />
          <Slider
            minimumValue={spec.min ?? 0}
            maximumValue={spec.max ?? 10}
            step={step}
            value={numV}
            onSlidingComplete={(val) => setKey(key, isInt ? Math.round(val) : Number(val.toFixed(3)))}
            minimumTrackTintColor={T.accent}
            maximumTrackTintColor={T.border}
            thumbTintColor={T.accent}
          />
          <View style={kRangeRow}>
            <Text style={kRangeText}>{spec.min ?? 0}</Text>
            <Text style={kRangeText}>{spec.max ?? 10}</Text>
          </View>
          {rejReason && <Text style={kReject}>⚠ {rejReason}</Text>}
        </View>
      );
    }

    if (spec.type === 'int_set' && spec.values) {
      return (
        <View>
          <RowHeader k={key} valueDisplay={<Text style={kVal}>{String(v)}</Text>} />
          <View style={kPillRow}>
            {spec.values.map(opt => {
              const sel = v === opt;
              return (
                <TouchableOpacity
                  key={opt}
                  style={[kPill, sel && kPillSel]}
                  onPress={() => setKey(key, opt)}
                  activeOpacity={0.7}
                >
                  <Text style={[kPillText, sel && kPillTextSel]}>{opt}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
          {rejReason && <Text style={kReject}>⚠ {rejReason}</Text>}
        </View>
      );
    }

    if (spec.type === 'enum' && spec.vocab) {
      return (
        <View>
          <RowHeader k={key} valueDisplay={<Text style={kVal}>{String(v || '—')}</Text>} />
          <View style={kPillRow}>
            {spec.vocab.map(opt => {
              const sel = v === opt;
              return (
                <TouchableOpacity
                  key={opt}
                  style={[kPill, sel && kPillSel]}
                  onPress={() => setKey(key, opt)}
                  activeOpacity={0.7}
                >
                  <Text style={[kPillText, sel && kPillTextSel]}>{opt}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
          {rejReason && <Text style={kReject}>⚠ {rejReason}</Text>}
        </View>
      );
    }

    if (spec.type === 'list[str]' && spec.vocab) {
      const arr: string[] = Array.isArray(v) ? v : [];
      return (
        <View>
          <RowHeader k={key} valueDisplay={<Text style={kVal}>{arr.length ? arr.join(' · ') : '—'}</Text>} />
          <View style={kPillRow}>
            {spec.vocab.map(opt => {
              const sel = arr.includes(opt);
              return (
                <TouchableOpacity
                  key={opt}
                  style={[kPill, sel && kPillSel]}
                  onPress={() => {
                    const next = sel ? arr.filter(x => x !== opt) : [...arr, opt];
                    setKey(key, next);
                  }}
                  activeOpacity={0.7}
                >
                  <Text style={[kPillText, sel && kPillTextSel]}>{opt}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
          {rejReason && <Text style={kReject}>⚠ {rejReason}</Text>}
        </View>
      );
    }

    if (spec.type === 'bool') {
      const on = !!v;
      const dirty = key in draft;
      const atDef = isAtDefault(key);
      return (
        <View>
          <View style={kRowHead}>
            <Text style={[kLabel, dirty && { color: T.accent }]}>{KEY_LABEL[key] || key}</Text>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <TouchableOpacity
                style={[kToggle, on && kToggleOn]}
                onPress={() => setKey(key, !on)}
                activeOpacity={0.7}
                accessibilityRole="switch"
                accessibilityState={{ checked: on }}
                accessibilityLabel={KEY_LABEL[key] || key}
              >
                <View style={[kToggleKnob, on && kToggleKnobOn]} />
              </TouchableOpacity>
              <DialResetIcon
                visible={!atDef}
                onPress={() => resetSingleDial(key)}
                label={KEY_LABEL[key] || key}
              />
            </View>
          </View>
          {rejReason && <Text style={kReject}>⚠ {rejReason}</Text>}
        </View>
      );
    }

    return null;
  };

  // ─── Render ─────────────────────────────────────────────────────
  if (loading) {
    return (
      <View style={panelLoading}>
        <ActivityIndicator color={T.accent} size="large" />
        <Text style={{ color: T.textMuted, marginTop: 12, fontSize: 13 }}>Loading ML schema…</Text>
      </View>
    );
  }

  if (!schema) {
    return (
      <View style={panelLoading}>
        <Ionicons name="warning-outline" size={32} color={T.warning} />
        <Text style={{ color: T.textMuted, marginTop: 8, fontSize: 13 }}>Failed to load schema.</Text>
        <TouchableOpacity onPress={onClose} style={{ marginTop: 14, padding: 10 }}>
          <Text style={{ color: T.accent, fontSize: 14, fontWeight: '700' }}>Close</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const dirtyCount = Object.keys(draft).length;

  return (
    <View style={{ flex: 1, backgroundColor: T.bg }}>
      {/* Header */}
      <View style={hdr}>
        <TouchableOpacity onPress={onClose} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
          <Ionicons name="arrow-back-outline" size={22} color={T.text} />
        </TouchableOpacity>
        <View style={{ flex: 1, marginLeft: 12 }}>
          <Text style={hdrTitle}>ML Console</Text>
          <Text style={hdrSub}>{Object.keys(schema).length} dials · {dirtyCount} unsaved</Text>
        </View>
        <TouchableOpacity
          onPress={handleReset}
          disabled={saving}
          style={[resetBtn, saving && { opacity: 0.4 }]}
          activeOpacity={0.7}
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
        >
          <Ionicons name="refresh-outline" size={16} color={T.textDim} />
        </TouchableOpacity>
        <TouchableOpacity
          onPress={handleSave}
          disabled={!dirtyCount || saving}
          style={[saveBtn, (!dirtyCount || saving) && { opacity: 0.4 }]}
          activeOpacity={0.7}
        >
          {saving
            ? <ActivityIndicator color="#fff" size="small" />
            : <Text style={saveBtnText}>Save {dirtyCount > 0 ? `(${dirtyCount})` : ''}</Text>}
        </TouchableOpacity>
      </View>

      {/* Flash banner */}
      {!!savedFlash && (
        <View style={flashBanner}>
          <Ionicons name="checkmark-circle" size={14} color={T.success} />
          <Text style={flashText}>{savedFlash}</Text>
        </View>
      )}

      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 80 }}>
        {GROUP_ORDER.map(group => {
          const keys = Object.keys(schema).filter(k => KEY_GROUP[k] === group);
          if (!keys.length) return null;
          return (
            <View key={group} style={{ marginBottom: 18 }}>
              <Text style={groupTitle}>{group}</Text>
              <View style={groupCard}>
                {keys.map((k, idx) => (
                  <View
                    key={k}
                    style={[rowWrap, idx < keys.length - 1 && rowDivider]}
                    accessible
                    accessibilityRole="adjustable"
                    accessibilityLabel={KEY_LABEL[k] || k}
                    // @ts-ignore RN-web maps focusable + tabIndex through accessible/focusable props
                    focusable
                    tabIndex={0}
                  >
                    {renderControl(k, schema[k])}
                  </View>
                ))}
              </View>
            </View>
          );
        })}
        <Text style={footerHelp}>
          Changes apply to this build only. Use the slider, picker, or toggle, then tap Save.
          {Platform.OS === 'web' ? ' Tip: press ⌘/Ctrl + S to save quickly.' : ''}
          {' '}Out-of-range values will be rejected with a reason shown inline.
        </Text>
        {/* 2026-05-15 — Cache age + revalidating indicator */}
        {cacheTs && (
          <Text style={cacheAgeText}>
            Schema cached {humanizeAge(Date.now() - cacheTs)} ago
            {revalidating ? ' · revalidating…' : ''}
          </Text>
        )}
      </ScrollView>

      {/* 2026-05-15 — Reset diff preview modal */}
      {resetDiff && schema && (
        <View style={diffOverlay}>
          <View style={diffCard}>
            <View style={diffHeader}>
              <Ionicons name="refresh-outline" size={18} color={T.warning} />
              <Text style={diffTitle}>Reset {resetDiff.length} dial{resetDiff.length > 1 ? 's' : ''}?</Text>
              <TouchableOpacity onPress={() => setResetDiff(null)} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                <Ionicons name="close" size={20} color={T.textDim} />
              </TouchableOpacity>
            </View>
            <Text style={diffSubtitle}>Review changes before staging. Nothing is saved until you tap Save.</Text>
            <ScrollView style={{ maxHeight: 360 }} contentContainerStyle={{ paddingBottom: 4 }}>
              {resetDiff.map(({ key, from, to }) => (
                <View key={key} style={diffRow}>
                  <Text style={diffKey}>{KEY_LABEL[key] || key}</Text>
                  <View style={diffArrowRow}>
                    <Text style={diffFrom} numberOfLines={1}>{formatVal(from)}</Text>
                    <Ionicons name="arrow-forward-outline" size={12} color={T.textMuted} style={{ marginHorizontal: 6 }} />
                    <Text style={diffTo} numberOfLines={1}>{formatVal(to)}</Text>
                  </View>
                </View>
              ))}
            </ScrollView>
            <View style={diffActions}>
              <TouchableOpacity style={diffBtnSecondary} onPress={() => setResetDiff(null)} activeOpacity={0.7}>
                <Text style={diffBtnSecondaryText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={diffBtnPrimary} onPress={confirmReset} activeOpacity={0.7}>
                <Text style={diffBtnPrimaryText}>Stage Reset</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      )}
    </View>
  );
};

// ─── Utility: humanize cache age + format dial values for diff ──────
const humanizeAge = (ms: number): string => {
  if (ms < 0) return 'just now';
  const s = Math.floor(ms / 1000);
  if (s < 5) return 'just now';
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  const d = Math.floor(h / 24);
  return `${d}d`;
};

const formatVal = (v: any): string => {
  if (v === undefined || v === null) return '—';
  if (typeof v === 'boolean') return v ? 'on' : 'off';
  if (Array.isArray(v)) return v.length ? v.join(' · ') : '[]';
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(2);
  return String(v);
};

const localStyles = StyleSheet.create({
  panelLoading: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: T.bg },
  hdr: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: 14, paddingVertical: 12,
    backgroundColor: T.surface,
    borderBottomWidth: 1, borderBottomColor: T.border,
  },
  hdrTitle: { color: T.text, fontSize: 16, fontWeight: '800' },
  hdrSub:   { color: T.accentLight, fontSize: 11, marginTop: 1 },
  saveBtn: {
    paddingHorizontal: 14, paddingVertical: 8,
    borderRadius: 8, backgroundColor: T.accent,
    minWidth: 76, alignItems: 'center',
  },
  saveBtnText: { color: '#fff', fontSize: 13, fontWeight: '800' },
  resetBtn: {
    paddingHorizontal: 10, paddingVertical: 8,
    borderRadius: 8, borderWidth: 1, borderColor: T.border,
    backgroundColor: T.bg,
    marginRight: 8,
    alignItems: 'center', justifyContent: 'center',
  },
  flashBanner: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: T.success + '20',
    paddingHorizontal: 14, paddingVertical: 8,
    borderBottomWidth: 1, borderBottomColor: T.success + '40',
  },
  flashText: { color: T.success, fontSize: 12, fontWeight: '700' },
  groupTitle: {
    color: T.textMuted, fontSize: 11, fontWeight: '800',
    textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6,
  },
  groupCard: {
    backgroundColor: T.surface, borderRadius: 12,
    borderWidth: 1, borderColor: T.border,
    paddingHorizontal: 12, paddingTop: 8,
  },
  rowWrap: { paddingVertical: 10 },
  rowDivider: { borderBottomWidth: 0.5, borderBottomColor: T.border },
  rowHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 },
  label:   { color: T.text, fontSize: 13, fontWeight: '700' },
  val:     { color: T.accentLight, fontSize: 12, fontWeight: '700' },
  rangeRow: { flexDirection: 'row', justifyContent: 'space-between', marginTop: -6 },
  rangeText: { color: T.textMuted, fontSize: 9 },
  pillRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 4 },
  pill: {
    paddingHorizontal: 10, paddingVertical: 6,
    borderRadius: 999, borderWidth: 1, borderColor: T.border,
    backgroundColor: T.bg,
  },
  pillSel: { borderColor: T.accent, backgroundColor: T.accent + '22' },
  pillText: { color: T.textDim, fontSize: 11, fontWeight: '700' },
  pillTextSel: { color: T.accent },
  toggle: {
    width: 44, height: 24, borderRadius: 12,
    backgroundColor: T.border, padding: 2, justifyContent: 'center',
  },
  toggleOn: { backgroundColor: T.accent },
  toggleKnob: {
    width: 20, height: 20, borderRadius: 10,
    backgroundColor: '#fff',
    alignSelf: 'flex-start',
  },
  toggleKnobOn: { alignSelf: 'flex-end' },
  reject: { color: T.warning, fontSize: 11, marginTop: 4 },
  footerHelp: { color: T.textMuted, fontSize: 11, lineHeight: 16, textAlign: 'center', marginTop: 8, marginBottom: 6 },
  cacheAgeText: { color: T.textMuted, fontSize: 10, textAlign: 'center', marginBottom: 20, fontStyle: 'italic' },
  // 2026-05-15 — Reset diff modal
  diffOverlay: {
    position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.65)',
    alignItems: 'center', justifyContent: 'center',
    paddingHorizontal: 20,
  },
  diffCard: {
    width: '100%', maxWidth: 420,
    backgroundColor: T.surface,
    borderRadius: 14, borderWidth: 1, borderColor: T.border,
    padding: 16,
  },
  diffHeader: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 },
  diffTitle: { flex: 1, color: T.text, fontSize: 15, fontWeight: '800' },
  diffSubtitle: { color: T.textMuted, fontSize: 11, lineHeight: 15, marginBottom: 10 },
  diffRow: {
    paddingVertical: 8, borderBottomWidth: 0.5, borderBottomColor: T.border,
  },
  diffKey: { color: T.text, fontSize: 12, fontWeight: '700', marginBottom: 4 },
  diffArrowRow: { flexDirection: 'row', alignItems: 'center' },
  diffFrom: { color: T.textDim, fontSize: 11, fontFamily: 'monospace' as any, maxWidth: 130 },
  diffTo:   { color: T.accent, fontSize: 11, fontFamily: 'monospace' as any, fontWeight: '700', maxWidth: 130 },
  diffActions: { flexDirection: 'row', gap: 8, marginTop: 12 },
  diffBtnSecondary: {
    flex: 1, paddingVertical: 10, alignItems: 'center', borderRadius: 8,
    borderWidth: 1, borderColor: T.border, backgroundColor: T.bg,
  },
  diffBtnSecondaryText: { color: T.textDim, fontSize: 13, fontWeight: '700' },
  diffBtnPrimary: {
    flex: 1, paddingVertical: 10, alignItems: 'center', borderRadius: 8,
    backgroundColor: T.warning,
  },
  diffBtnPrimaryText: { color: '#fff', fontSize: 13, fontWeight: '800' },
});

const panelLoading = localStyles.panelLoading;
const hdr          = localStyles.hdr;
const hdrTitle     = localStyles.hdrTitle;
const hdrSub       = localStyles.hdrSub;
const saveBtn      = localStyles.saveBtn;
const saveBtnText  = localStyles.saveBtnText;
const resetBtn     = localStyles.resetBtn;
const flashBanner  = localStyles.flashBanner;
const flashText    = localStyles.flashText;
const groupTitle   = localStyles.groupTitle;
const groupCard    = localStyles.groupCard;
const rowWrap      = localStyles.rowWrap;
const rowDivider   = localStyles.rowDivider;
const kRowHead     = localStyles.rowHead;
const kLabel       = localStyles.label;
const kVal         = localStyles.val;
const kRangeRow    = localStyles.rangeRow;
const kRangeText   = localStyles.rangeText;
const kPillRow     = localStyles.pillRow;
const kPill        = localStyles.pill;
const kPillSel     = localStyles.pillSel;
const kPillText    = localStyles.pillText;
const kPillTextSel = localStyles.pillTextSel;
const kToggle      = localStyles.toggle;
const kToggleOn    = localStyles.toggleOn;
const kToggleKnob  = localStyles.toggleKnob;
const kToggleKnobOn = localStyles.toggleKnobOn;
const kReject      = localStyles.reject;
const footerHelp   = localStyles.footerHelp;
const cacheAgeText = localStyles.cacheAgeText;
const diffOverlay  = localStyles.diffOverlay;
const diffCard     = localStyles.diffCard;
const diffHeader   = localStyles.diffHeader;
const diffTitle    = localStyles.diffTitle;
const diffSubtitle = localStyles.diffSubtitle;
const diffRow      = localStyles.diffRow;
const diffKey      = localStyles.diffKey;
const diffArrowRow = localStyles.diffArrowRow;
const diffFrom     = localStyles.diffFrom;
const diffTo       = localStyles.diffTo;
const diffActions  = localStyles.diffActions;
const diffBtnSecondary     = localStyles.diffBtnSecondary;
const diffBtnSecondaryText = localStyles.diffBtnSecondaryText;
const diffBtnPrimary       = localStyles.diffBtnPrimary;
const diffBtnPrimaryText   = localStyles.diffBtnPrimaryText;
