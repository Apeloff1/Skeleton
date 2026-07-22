/**
 * ╔═══════════════════════════════════════════════════════════════════════════╗
 * ║    THERMAL MONITOR v1.0 — Overheat Mitigation System Dashboard          ║
 * ║                                                                           ║
 * ║    Full visual thermal dashboard for 25,994 agents                       ║
 * ║    • Real-time department heat gauges with color-coded zones             ║
 * ║    • Global thermal overview with zone distribution                      ║
 * ║    • Alert feed with severity levels                                     ║
 * ║    • Warm standby redundancy pool status                                 ║
 * ║    • Cooldown controls (active, flush, emergency)                        ║
 * ║    • Thermal simulation runner with scenario picker                      ║
 * ╚═══════════════════════════════════════════════════════════════════════════╝
 */

import { NATIVE_DRIVER } from '../../src/utils/platformStyles';
import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView,
  Modal, ActivityIndicator, Animated, RefreshControl,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Constants from 'expo-constants';

import { apiFetch } from '../../utils/apiController';
const API_BASE = (() => {
  if (typeof window !== 'undefined' && (window as any).location?.origin && !(window as any).location.origin.startsWith('file:')) {
    return (window as any).location.origin.replace(/\/+$/, '');
  }
  return (Constants.expoConfig?.extra?.EXPO_PUBLIC_BACKEND_URL as string)
    || process.env.EXPO_PUBLIC_BACKEND_URL || '';
})();


// ═══════════════ TYPES ═══════════════

interface ZoneClassification {
  zone: string;
  color: string;
  icon: string;
  severity: number;
  label: string;
}

interface ZoneDistribution {
  nominal: number;
  warm: number;
  hot: number;
  warning: number;
  critical: number;
  meltdown: number;
}

interface StandbyPool {
  total_standbys: number;
  standbys_idle: number;
  standbys_active: number;
  coverage_percent: number;
}

interface Department {
  department_id: string;
  department_name: string;
  icon: string;
  agent_count: number;
  avg_heat: number;
  max_heat: number;
  min_heat: number;
  classification: ZoneClassification;
  zone_distribution: ZoneDistribution;
  standby_pool: StandbyPool;
  health_score: number;
  heat_multiplier: number;
}

interface Alert {
  level: string;
  department: string;
  department_id: string;
  message: string;
  icon: string;
  color: string;
  timestamp: string;
}

interface ThermalStatus {
  system: string;
  timestamp: string;
  global_stats: {
    total_agents: number;
    global_avg_heat: number;
    global_max_heat: number;
    global_classification: ZoneClassification;
    global_health_score: number;
    zone_totals: ZoneDistribution;
    redundancy_overview: {
      total_standbys: number;
      standbys_active: number;
      standbys_idle: number;
      redundancy_utilization: number;
    };
    cooling_config: {
      passive_cool_rate: number;
      active_cool_flush: number;
      reclaim_threshold: number;
      thresholds: Record<string, number>;
    };
  };
  departments: Department[];
  active_alerts: Alert[];
  alert_count: number;
  philosophy: string;
}

interface SimResult {
  simulation: { scenario: string; intensity: number; duration_seconds: number; departments_tested: number };
  summary: {
    critical_before: number;
    critical_after: number;
    critical_delta: number;
    total_standby_demand: number;
    total_standby_available: number;
    redundancy_sufficient: boolean;
    system_verdict: string;
  };
  recommendation: string;
  department_results: any[];
}

interface ThermalMonitorModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
}

type TabView = 'overview' | 'departments' | 'alerts' | 'redundancy' | 'simulate';

// ═══════════════ HEAT GAUGE COMPONENT ═══════════════

const HeatGauge: React.FC<{ heat: number; size?: number; label?: string }> = ({ heat, size = 60, label }) => {
  const getColor = (h: number) => {
    if (h >= 95) return '#DC2626';
    if (h >= 85) return '#F97316';
    if (h >= 65) return '#EAB308';
    if (h >= 40) return '#3B82F6';
    return '#22C55E';
  };

  const fillPercent = Math.min(heat / 100, 1);
  const color = getColor(heat);

  return (
    <View style={{ alignItems: 'center' }}>
      <View style={[gaugeStyles.outer, { width: size, height: size, borderColor: color }]}>
        <View style={[gaugeStyles.fill, {
          backgroundColor: color,
          height: `${fillPercent * 100}%` as any,
          opacity: 0.3 + fillPercent * 0.5,
        }]} />
        <Text style={[gaugeStyles.value, { fontSize: size * 0.28, color }]}>{Math.round(heat)}°</Text>
      </View>
      {label && <Text style={gaugeStyles.label} numberOfLines={1}>{label}</Text>}
    </View>
  );
};

const gaugeStyles = StyleSheet.create({
  outer: {
    borderRadius: 999, borderWidth: 3, overflow: 'hidden',
    justifyContent: 'center', alignItems: 'center',
  },
  fill: {
    position: 'absolute', bottom: 0, left: 0, right: 0,
  },
  value: {
    fontWeight: '900', zIndex: 1,
  },
  label: {
    fontSize: 10, color: '#94A3B8', marginTop: 4, maxWidth: 70, textAlign: 'center',
  },
});

// ═══════════════ ZONE BAR COMPONENT ═══════════════

const ZoneBar: React.FC<{ zones: ZoneDistribution; total: number }> = ({ zones, total }) => {
  if (total === 0) return null;
  const segments = [
    { key: 'nominal', count: zones.nominal, color: '#22C55E' },
    { key: 'warm', count: zones.warm, color: '#3B82F6' },
    { key: 'hot', count: zones.hot, color: '#EAB308' },
    { key: 'warning', count: zones.warning, color: '#F97316' },
    { key: 'critical', count: zones.critical, color: '#EF4444' },
    { key: 'meltdown', count: zones.meltdown, color: '#7F1D1D' },
  ];

  return (
    <View style={zoneStyles.container}>
      <View style={zoneStyles.bar}>
        {segments.map(s => {
          const pct = (s.count / total) * 100;
          if (pct < 0.5) return null;
          return (
            <View key={s.key} style={[zoneStyles.segment, { width: `${pct}%` as any, backgroundColor: s.color }]} />
          );
        })}
      </View>
      <View style={zoneStyles.legend}>
        {segments.filter(s => s.count > 0).map(s => (
          <View key={s.key} style={zoneStyles.legendItem}>
            <View style={[zoneStyles.dot, { backgroundColor: s.color }]} />
            <Text style={zoneStyles.legendText}>{s.count}</Text>
          </View>
        ))}
      </View>
    </View>
  );
};

const zoneStyles = StyleSheet.create({
  container: { marginTop: 6 },
  bar: { flexDirection: 'row', height: 8, borderRadius: 4, overflow: 'hidden', backgroundColor: '#1E293B' },
  segment: { height: '100%' },
  legend: { flexDirection: 'row', flexWrap: 'wrap', marginTop: 4, gap: 6 },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 3 },
  dot: { width: 6, height: 6, borderRadius: 3 },
  legendText: { fontSize: 10, color: '#94A3B8' },
});

// ═══════════════ MAIN MODAL ═══════════════

export const ThermalMonitorModal: React.FC<ThermalMonitorModalProps> = ({ visible, onClose, colors }) => {
  const [tab, setTab] = useState<TabView>('overview');
  const [status, setStatus] = useState<ThermalStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [simRunning, setSimRunning] = useState(false);
  const [simResult, setSimResult] = useState<SimResult | null>(null);
  const [simScenario, setSimScenario] = useState('load_spike');
  const [simIntensity, setSimIntensity] = useState(0.7);
  const [expandedDept, setExpandedDept] = useState<string | null>(null);
  const pulseAnim = useRef(new Animated.Value(1)).current;

  // Pulse animation for alerts
  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulseAnim, { toValue: 0.6, duration: 800, useNativeDriver: NATIVE_DRIVER }),
        Animated.timing(pulseAnim, { toValue: 1, duration: 800, useNativeDriver: NATIVE_DRIVER }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [pulseAnim]);

  const fetchStatus = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    try {
      const res = await apiFetch(`${API_BASE}/api/game-factory/thermal/status`);
      if (res.ok) {
        const data = await res.json();
        setStatus(data);
      }
    } catch (e) {
      console.log('Thermal fetch error:', e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    if (visible) fetchStatus();
  }, [visible, fetchStatus]);

  const runSimulation = async () => {
    setSimRunning(true);
    setSimResult(null);
    try {
      const res = await apiFetch(`${API_BASE}/api/game-factory/thermal/simulate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scenario: simScenario,
          intensity: simIntensity,
          duration_seconds: 60,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setSimResult(data);
      }
    } catch (e) {
      console.log('Simulation error:', e);
    } finally {
      setSimRunning(false);
    }
  };

  const triggerCooldown = async (deptId: string, agentId: string, mode: string) => {
    try {
      await apiFetch(`${API_BASE}/api/game-factory/thermal/cooldown`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_id: agentId, department_id: deptId, mode }),
      });
      fetchStatus();
    } catch (e) {
      console.log('Cooldown error:', e);
    }
  };

  const TABS: { id: TabView; label: string; icon: string }[] = [
    { id: 'overview', label: 'Overview', icon: 'speedometer' },
    { id: 'departments', label: 'Depts', icon: 'grid' },
    { id: 'alerts', label: 'Alerts', icon: 'warning' },
    { id: 'redundancy', label: 'Standby', icon: 'shield-checkmark' },
    { id: 'simulate', label: 'Simulate', icon: 'flask' },
  ];

  const SCENARIOS = [
    { id: 'load_spike', label: 'Load Spike', icon: 'flash', color: '#F97316', desc: 'Sudden burst of tasks' },
    { id: 'sustained_load', label: 'Sustained Load', icon: 'trending-up', color: '#EAB308', desc: 'Continuous heavy usage' },
    { id: 'cascade_failure', label: 'Cascade Failure', icon: 'nuclear', color: '#DC2626', desc: 'Chain reaction overheat' },
    { id: 'cooldown_wave', label: 'Cooldown Wave', icon: 'snow', color: '#3B82F6', desc: 'System-wide cooling' },
  ];

  const gs = status?.global_stats;

  // ─── RENDER TABS ───────────────────────────────────────────────────────────

  const renderOverview = () => {
    if (!status || !gs) return null;
    const zoneTotals = gs.zone_totals;
    const totalAgents = gs.total_agents;
    const redun = gs.redundancy_overview;

    return (
      <View>
        {/* Global Heat */}
        <View style={s.card}>
          <View style={s.cardHeader}>
            <Ionicons name="thermometer" size={20} color={gs.global_classification.color} />
            <Text style={s.cardTitle}>Global Thermal Status</Text>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-around', marginTop: 12 }}>
            <HeatGauge heat={gs.global_avg_heat} size={80} label="AVG HEAT" />
            <View style={{ alignItems: 'center' }}>
              <Text style={[s.bigNumber, { color: gs.global_classification.color }]}>
                {gs.global_health_score}%
              </Text>
              <Text style={s.subLabel}>HEALTH SCORE</Text>
            </View>
            <HeatGauge heat={gs.global_max_heat} size={80} label="PEAK HEAT" />
          </View>
          <View style={[s.statusBadge, { backgroundColor: gs.global_classification.color + '22', borderColor: gs.global_classification.color }]}>
            <Ionicons name={gs.global_classification.icon as any} size={16} color={gs.global_classification.color} />
            <Text style={[s.statusText, { color: gs.global_classification.color }]}>
              {gs.global_classification.label}
            </Text>
          </View>
        </View>

        {/* Zone Distribution */}
        <View style={s.card}>
          <Text style={s.cardTitle}>Zone Distribution — {totalAgents} Agents</Text>
          <ZoneBar zones={zoneTotals} total={totalAgents} />
          <View style={{ marginTop: 12 }}>
            {[
              { label: 'Nominal', count: zoneTotals.nominal, color: '#22C55E', icon: 'snow' },
              { label: 'Warm', count: zoneTotals.warm, color: '#3B82F6', icon: 'sunny' },
              { label: 'Hot', count: zoneTotals.hot, color: '#EAB308', icon: 'thermometer' },
              { label: 'Warning', count: zoneTotals.warning, color: '#F97316', icon: 'warning' },
              { label: 'Critical', count: zoneTotals.critical, color: '#EF4444', icon: 'flame' },
              { label: 'Meltdown', count: zoneTotals.meltdown, color: '#7F1D1D', icon: 'skull' },
            ].map(z => (
              <View key={z.label} style={s.zoneRow}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Ionicons name={z.icon as any} size={14} color={z.color} />
                  <Text style={[s.zoneLabel, { color: z.color }]}>{z.label}</Text>
                </View>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Text style={s.zoneCount}>{z.count}</Text>
                  <Text style={s.zonePct}>({((z.count / totalAgents) * 100).toFixed(1)}%)</Text>
                </View>
              </View>
            ))}
          </View>
        </View>

        {/* Redundancy Overview */}
        <View style={s.card}>
          <View style={s.cardHeader}>
            <Ionicons name="shield-checkmark" size={20} color="#8B5CF6" />
            <Text style={s.cardTitle}>Warm Standby Pool</Text>
          </View>
          <View style={{ flexDirection: 'row', justifyContent: 'space-around', marginTop: 12 }}>
            <View style={{ alignItems: 'center' }}>
              <Text style={[s.bigNumber, { color: '#8B5CF6' }]}>{redun.total_standbys}</Text>
              <Text style={s.subLabel}>TOTAL</Text>
            </View>
            <View style={{ alignItems: 'center' }}>
              <Text style={[s.bigNumber, { color: '#22C55E' }]}>{redun.standbys_idle}</Text>
              <Text style={s.subLabel}>IDLE</Text>
            </View>
            <View style={{ alignItems: 'center' }}>
              <Text style={[s.bigNumber, { color: '#F97316' }]}>{redun.standbys_active}</Text>
              <Text style={s.subLabel}>ACTIVE</Text>
            </View>
            <View style={{ alignItems: 'center' }}>
              <Text style={[s.bigNumber, { color: '#EAB308' }]}>{redun.redundancy_utilization}%</Text>
              <Text style={s.subLabel}>UTILIZED</Text>
            </View>
          </View>
        </View>

        {/* Philosophy */}
        <View style={[s.card, { borderLeftWidth: 3, borderLeftColor: '#F97316' }]}>
          <Text style={s.philosophy}>{status.philosophy}</Text>
        </View>
      </View>
    );
  };

  const renderDepartments = () => {
    if (!status) return null;
    const depts = [...status.departments].sort((a, b) => b.avg_heat - a.avg_heat);

    return (
      <View>
        <Text style={s.sectionTitle}>Departments by Heat (Hottest First)</Text>
        {depts.map(dept => {
          const isExpanded = expandedDept === dept.department_id;
          return (
            <TouchableOpacity
              key={dept.department_id}
              style={[s.card, { borderLeftWidth: 3, borderLeftColor: dept.classification.color }]}
              onPress={() => setExpandedDept(isExpanded ? null : dept.department_id)}
              activeOpacity={0.7}
            >
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flex: 1 }}>
                  <Ionicons name={(dept.icon || 'help') as any} size={20} color={dept.classification.color} />
                  <View style={{ flex: 1 }}>
                    <Text style={s.deptName} numberOfLines={1}>{dept.department_name}</Text>
                    <Text style={s.deptSub}>{dept.agent_count} agents • x{dept.heat_multiplier} mult</Text>
                  </View>
                </View>
                <HeatGauge heat={dept.avg_heat} size={44} />
              </View>

              <ZoneBar zones={dept.zone_distribution} total={dept.agent_count} />

              {isExpanded && (
                <View style={{ marginTop: 12, padding: 8, backgroundColor: '#0F172A', borderRadius: 8 }}>
                  <View style={s.detailRow}>
                    <Text style={s.detailLabel}>Health Score</Text>
                    <Text style={[s.detailValue, { color: dept.health_score > 60 ? '#22C55E' : '#EF4444' }]}>
                      {dept.health_score}%
                    </Text>
                  </View>
                  <View style={s.detailRow}>
                    <Text style={s.detailLabel}>Peak Heat</Text>
                    <Text style={s.detailValue}>{dept.max_heat}°</Text>
                  </View>
                  <View style={s.detailRow}>
                    <Text style={s.detailLabel}>Standbys</Text>
                    <Text style={s.detailValue}>
                      {dept.standby_pool.standbys_active}/{dept.standby_pool.total_standbys} active
                    </Text>
                  </View>
                  {(dept.zone_distribution.critical > 0 || dept.zone_distribution.meltdown > 0) && (
                    <TouchableOpacity
                      style={s.cooldownBtn}
                      onPress={() => triggerCooldown(dept.department_id, `${dept.department_id}-agent-0`, 'flush')}
                    >
                      <Ionicons name="snow" size={16} color="#FFF" />
                      <Text style={s.cooldownBtnText}>Emergency Cooldown</Text>
                    </TouchableOpacity>
                  )}
                </View>
              )}
            </TouchableOpacity>
          );
        })}
      </View>
    );
  };

  const renderAlerts = () => {
    if (!status) return null;
    const alerts = status.active_alerts;

    return (
      <View>
        <View style={[s.card, { flexDirection: 'row', alignItems: 'center', gap: 8 }]}>
          <Animated.View style={{ opacity: pulseAnim }}>
            <Ionicons name="alert-circle" size={24} color={alerts.length > 0 ? '#EF4444' : '#22C55E'} />
          </Animated.View>
          <Text style={s.cardTitle}>
            {alerts.length > 0 ? `${alerts.length} Active Alert${alerts.length > 1 ? 's' : ''}` : 'All Clear'}
          </Text>
        </View>

        {alerts.length === 0 && (
          <View style={[s.card, { alignItems: 'center', paddingVertical: 32 }]}>
            <Ionicons name="checkmark-circle" size={48} color="#22C55E" />
            <Text style={{ color: '#22C55E', fontSize: 16, fontWeight: '700', marginTop: 8 }}>
              No Critical Alerts
            </Text>
            <Text style={{ color: '#94A3B8', fontSize: 12, marginTop: 4 }}>
              All thermal zones within safe parameters
            </Text>
          </View>
        )}

        {alerts.map((alert, idx) => (
          <View key={idx} style={[s.card, { borderLeftWidth: 3, borderLeftColor: alert.color }]}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <Ionicons name={(alert.icon || 'warning') as any} size={18} color={alert.color} />
              <View style={[s.alertBadge, { backgroundColor: alert.color + '22' }]}>
                <Text style={[s.alertBadgeText, { color: alert.color }]}>{alert.level}</Text>
              </View>
              <Text style={s.alertDept}>{alert.department}</Text>
            </View>
            <Text style={s.alertMsg}>{alert.message}</Text>
          </View>
        ))}
      </View>
    );
  };

  const renderRedundancy = () => {
    if (!status) return null;
    const depts = status.departments;
    const gs2 = status.global_stats.redundancy_overview;

    return (
      <View>
        {/* Global Pool */}
        <View style={s.card}>
          <View style={s.cardHeader}>
            <Ionicons name="shield-checkmark" size={20} color="#8B5CF6" />
            <Text style={s.cardTitle}>Warm Standby Redundancy Pool</Text>
          </View>
          <View style={{ flexDirection: 'row', justifyContent: 'space-around', marginTop: 16 }}>
            {[
              { val: gs2.total_standbys, label: 'Total Pool', color: '#8B5CF6' },
              { val: gs2.standbys_idle, label: 'Ready', color: '#22C55E' },
              { val: gs2.standbys_active, label: 'Deployed', color: '#F97316' },
            ].map(item => (
              <View key={item.label} style={{ alignItems: 'center' }}>
                <Text style={[s.bigNumber, { color: item.color }]}>{item.val}</Text>
                <Text style={s.subLabel}>{item.label}</Text>
              </View>
            ))}
          </View>
          <View style={[s.progressBarOuter, { marginTop: 16 }]}>
            <View style={[s.progressBarInner, {
              width: `${gs2.redundancy_utilization}%` as any,
              backgroundColor: gs2.redundancy_utilization > 80 ? '#EF4444' : gs2.redundancy_utilization > 50 ? '#F97316' : '#22C55E',
            }]} />
          </View>
          <Text style={s.progressLabel}>{gs2.redundancy_utilization}% Utilized</Text>
        </View>

        {/* Per-Department Standby */}
        <Text style={s.sectionTitle}>Department Standby Status</Text>
        {depts.map(dept => {
          const pool = dept.standby_pool;
          const utilizationPct = pool.total_standbys > 0
            ? (pool.standbys_active / pool.total_standbys) * 100
            : 0;

          return (
            <View key={dept.department_id} style={[s.card, { paddingVertical: 10 }]}>
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flex: 1 }}>
                  <Ionicons name={(dept.icon || 'help') as any} size={16} color="#CBD5E1" />
                  <Text style={s.deptName} numberOfLines={1}>{dept.department_name}</Text>
                </View>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
                  <Text style={{ color: '#22C55E', fontSize: 12, fontWeight: '700' }}>
                    {pool.standbys_idle} ready
                  </Text>
                  <Text style={{ color: '#F97316', fontSize: 12, fontWeight: '700' }}>
                    {pool.standbys_active} active
                  </Text>
                </View>
              </View>
              <View style={[s.progressBarOuter, { marginTop: 6, height: 4 }]}>
                <View style={[s.progressBarInner, {
                  width: `${utilizationPct}%` as any,
                  backgroundColor: utilizationPct > 80 ? '#EF4444' : utilizationPct > 50 ? '#F97316' : '#22C55E',
                  height: 4,
                }]} />
              </View>
            </View>
          );
        })}
      </View>
    );
  };

  const renderSimulate = () => (
    <View>
      <View style={s.card}>
        <View style={s.cardHeader}>
          <Ionicons name="flask" size={20} color="#EC4899" />
          <Text style={s.cardTitle}>Thermal Simulation</Text>
        </View>
        <Text style={{ color: '#94A3B8', fontSize: 12, marginTop: 4 }}>
          Run stress scenarios to test system resilience
        </Text>
      </View>

      {/* Scenario Picker */}
      <Text style={s.sectionTitle}>Select Scenario</Text>
      <View style={{ gap: 8 }}>
        {SCENARIOS.map(sc => (
          <TouchableOpacity
            key={sc.id}
            style={[s.card, {
              borderLeftWidth: 3,
              borderLeftColor: simScenario === sc.id ? sc.color : '#334155',
              opacity: simScenario === sc.id ? 1 : 0.7,
            }]}
            onPress={() => setSimScenario(sc.id)}
          >
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              <Ionicons name={sc.icon as any} size={22} color={sc.color} />
              <View style={{ flex: 1 }}>
                <Text style={s.deptName}>{sc.label}</Text>
                <Text style={{ color: '#94A3B8', fontSize: 11 }}>{sc.desc}</Text>
              </View>
              {simScenario === sc.id && <Ionicons name="checkmark-circle" size={20} color={sc.color} />}
            </View>
          </TouchableOpacity>
        ))}
      </View>

      {/* Intensity */}
      <View style={[s.card, { marginTop: 8 }]}>
        <Text style={s.cardTitle}>Intensity: {Math.round(simIntensity * 100)}%</Text>
        <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
          {[0.3, 0.5, 0.7, 0.9, 1.0].map(val => (
            <TouchableOpacity
              key={val}
              style={[s.intensityBtn, simIntensity === val && s.intensityBtnActive]}
              onPress={() => setSimIntensity(val)}
            >
              <Text style={[s.intensityBtnText, simIntensity === val && { color: '#FFF' }]}>
                {Math.round(val * 100)}%
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {/* Run Button */}
      <TouchableOpacity
        style={[s.runSimBtn, simRunning && { opacity: 0.5 }]}
        onPress={runSimulation}
        disabled={simRunning}
      >
        {simRunning ? (
          <ActivityIndicator color="#FFF" size="small" />
        ) : (
          <Ionicons name="play" size={20} color="#FFF" />
        )}
        <Text style={s.runSimBtnText}>
          {simRunning ? 'Simulating...' : 'Run Simulation'}
        </Text>
      </TouchableOpacity>

      {/* Results */}
      {simResult && (
        <View style={[s.card, { marginTop: 8, borderLeftWidth: 3, borderLeftColor: simResult.summary.redundancy_sufficient ? '#22C55E' : '#EF4444' }]}>
          <View style={s.cardHeader}>
            <Ionicons
              name={simResult.summary.redundancy_sufficient ? 'checkmark-circle' : 'alert-circle'}
              size={22}
              color={simResult.summary.redundancy_sufficient ? '#22C55E' : '#EF4444'}
            />
            <Text style={[s.cardTitle, { color: simResult.summary.redundancy_sufficient ? '#22C55E' : '#EF4444' }]}>
              Verdict: {simResult.summary.system_verdict}
            </Text>
          </View>

          <View style={{ marginTop: 12, gap: 6 }}>
            <View style={s.detailRow}>
              <Text style={s.detailLabel}>Critical Before</Text>
              <Text style={s.detailValue}>{simResult.summary.critical_before}</Text>
            </View>
            <View style={s.detailRow}>
              <Text style={s.detailLabel}>Critical After</Text>
              <Text style={[s.detailValue, { color: '#EF4444' }]}>{simResult.summary.critical_after}</Text>
            </View>
            <View style={s.detailRow}>
              <Text style={s.detailLabel}>Delta</Text>
              <Text style={[s.detailValue, { color: simResult.summary.critical_delta > 0 ? '#EF4444' : '#22C55E' }]}>
                {simResult.summary.critical_delta > 0 ? '+' : ''}{simResult.summary.critical_delta}
              </Text>
            </View>
            <View style={s.detailRow}>
              <Text style={s.detailLabel}>Standby Demand</Text>
              <Text style={s.detailValue}>{simResult.summary.total_standby_demand}</Text>
            </View>
            <View style={s.detailRow}>
              <Text style={s.detailLabel}>Standby Available</Text>
              <Text style={s.detailValue}>{simResult.summary.total_standby_available}</Text>
            </View>
          </View>

          <Text style={{ color: '#CBD5E1', fontSize: 12, marginTop: 10, fontStyle: 'italic' }}>
            {simResult.recommendation}
          </Text>
        </View>
      )}
    </View>
  );

  // ─── MAIN RENDER ───────────────────────────────────────────────────────────

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View style={s.overlay}>
        <View style={s.container}>
          {/* Header */}
          <View style={s.header}>
            <TouchableOpacity onPress={onClose} style={s.backBtn}>
              <Ionicons name="chevron-back" size={24} color="#FFF" />
            </TouchableOpacity>
            <View style={{ flex: 1, alignItems: 'center' }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <Ionicons name="flame" size={20} color="#F97316" />
                <Text style={s.headerTitle}>Thermal Monitor</Text>
              </View>
              <Text style={s.headerSub}>Overheat Mitigation System</Text>
            </View>
            <TouchableOpacity onPress={() => fetchStatus(true)} style={s.refreshBtn}>
              <Ionicons name="refresh" size={20} color="#94A3B8" />
            </TouchableOpacity>
          </View>

          {/* Tab Bar */}
          <View style={s.tabBar}>
            {TABS.map(t => (
              <TouchableOpacity
                key={t.id}
                style={[s.tab, tab === t.id && s.tabActive]}
                onPress={() => setTab(t.id)}
              >
                <Ionicons
                  name={t.icon as any}
                  size={16}
                  color={tab === t.id ? '#F97316' : '#64748B'}
                />
                <Text style={[s.tabText, tab === t.id && s.tabTextActive]}>
                  {t.label}
                </Text>
                {t.id === 'alerts' && status && status.alert_count > 0 && (
                  <View style={s.alertDot}>
                    <Text style={s.alertDotText}>{Math.min(status.alert_count, 99)}</Text>
                  </View>
                )}
              </TouchableOpacity>
            ))}
          </View>

          {/* Content */}
          {loading ? (
            <View style={s.loadingContainer}>
              <ActivityIndicator size="large" color="#F97316" />
              <Text style={{ color: '#94A3B8', marginTop: 12 }}>Loading thermal data...</Text>
            </View>
          ) : (
            <ScrollView
              style={s.content}
              contentContainerStyle={{ paddingBottom: 40 }}
              refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => fetchStatus(true)} tintColor="#F97316" />}
              showsVerticalScrollIndicator={false}
            >
              {tab === 'overview' && renderOverview()}
              {tab === 'departments' && renderDepartments()}
              {tab === 'alerts' && renderAlerts()}
              {tab === 'redundancy' && renderRedundancy()}
              {tab === 'simulate' && renderSimulate()}
            </ScrollView>
          )}
        </View>
      </View>
    </Modal>
  );
};

// ═══════════════ STYLES ═══════════════

const s = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.6)',
  },
  container: {
    flex: 1,
    backgroundColor: '#0F172A',
    marginTop: 44,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    overflow: 'hidden',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 14,
    backgroundColor: '#1E293B',
    borderBottomWidth: 1,
    borderBottomColor: '#334155',
  },
  backBtn: {
    width: 36, height: 36, borderRadius: 18,
    backgroundColor: '#334155', justifyContent: 'center', alignItems: 'center',
  },
  refreshBtn: {
    width: 36, height: 36, borderRadius: 18,
    backgroundColor: '#1E293B', justifyContent: 'center', alignItems: 'center',
  },
  headerTitle: {
    fontSize: 18, fontWeight: '800', color: '#FFF',
  },
  headerSub: {
    fontSize: 11, color: '#94A3B8', marginTop: 2,
  },
  tabBar: {
    flexDirection: 'row',
    backgroundColor: '#1E293B',
    paddingHorizontal: 8,
    paddingBottom: 8,
    gap: 4,
  },
  tab: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: 4, paddingVertical: 8, borderRadius: 8,
    backgroundColor: '#0F172A',
  },
  tabActive: {
    backgroundColor: '#F97316' + '22',
    borderWidth: 1,
    borderColor: '#F97316' + '44',
  },
  tabText: {
    fontSize: 10, color: '#64748B', fontWeight: '600',
  },
  tabTextActive: {
    color: '#F97316',
  },
  alertDot: {
    backgroundColor: '#EF4444',
    borderRadius: 8,
    minWidth: 16,
    height: 16,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 4,
  },
  alertDotText: {
    color: '#FFF', fontSize: 9, fontWeight: '800',
  },
  content: {
    flex: 1, paddingHorizontal: 12, paddingTop: 8,
  },
  loadingContainer: {
    flex: 1, justifyContent: 'center', alignItems: 'center',
  },
  card: {
    backgroundColor: '#1E293B',
    borderRadius: 12,
    padding: 14,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: '#334155',
  },
  cardHeader: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
  },
  cardTitle: {
    color: '#E2E8F0', fontSize: 14, fontWeight: '700',
  },
  bigNumber: {
    fontSize: 28, fontWeight: '900',
  },
  subLabel: {
    fontSize: 9, color: '#64748B', fontWeight: '700', marginTop: 2,
    letterSpacing: 0.5,
  },
  statusBadge: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    alignSelf: 'center', paddingHorizontal: 14, paddingVertical: 6,
    borderRadius: 20, borderWidth: 1, marginTop: 14,
  },
  statusText: {
    fontSize: 12, fontWeight: '800',
  },
  zoneRow: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingVertical: 4,
  },
  zoneLabel: {
    fontSize: 12, fontWeight: '600',
  },
  zoneCount: {
    fontSize: 14, fontWeight: '800', color: '#E2E8F0',
  },
  zonePct: {
    fontSize: 11, color: '#64748B',
  },
  sectionTitle: {
    color: '#CBD5E1', fontSize: 14, fontWeight: '700',
    marginBottom: 8, marginTop: 4,
  },
  deptName: {
    color: '#E2E8F0', fontSize: 13, fontWeight: '700',
  },
  deptSub: {
    color: '#64748B', fontSize: 10, marginTop: 2,
  },
  detailRow: {
    flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 3,
  },
  detailLabel: {
    color: '#94A3B8', fontSize: 12,
  },
  detailValue: {
    color: '#E2E8F0', fontSize: 12, fontWeight: '700',
  },
  cooldownBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    backgroundColor: '#3B82F6', borderRadius: 8, paddingVertical: 8, marginTop: 8,
  },
  cooldownBtnText: {
    color: '#FFF', fontSize: 12, fontWeight: '700',
  },
  alertBadge: {
    paddingHorizontal: 8, paddingVertical: 2, borderRadius: 4,
  },
  alertBadgeText: {
    fontSize: 10, fontWeight: '800',
  },
  alertDept: {
    color: '#CBD5E1', fontSize: 12, fontWeight: '600',
  },
  alertMsg: {
    color: '#94A3B8', fontSize: 12,
  },
  philosophy: {
    color: '#F97316', fontSize: 12, fontStyle: 'italic', textAlign: 'center',
  },
  progressBarOuter: {
    height: 8, backgroundColor: '#334155', borderRadius: 4, overflow: 'hidden',
  },
  progressBarInner: {
    height: 8, borderRadius: 4,
  },
  progressLabel: {
    color: '#94A3B8', fontSize: 10, textAlign: 'center', marginTop: 4,
  },
  intensityBtn: {
    flex: 1, paddingVertical: 8, borderRadius: 8,
    backgroundColor: '#334155', alignItems: 'center',
  },
  intensityBtnActive: {
    backgroundColor: '#F97316',
  },
  intensityBtnText: {
    color: '#94A3B8', fontSize: 12, fontWeight: '700',
  },
  runSimBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    backgroundColor: '#EC4899', borderRadius: 12, paddingVertical: 14, marginTop: 12,
  },
  runSimBtnText: {
    color: '#FFF', fontSize: 16, fontWeight: '800',
  },
});

export default ThermalMonitorModal;
