/**
 * Original Dragon native puzzle editor: genuine 12×10 authored game content.
 *
 * Grid cells are symbolic source data (# wall, . floor, @ avatar, $ crate,
 * o target). This UI does not run game code or claim a legal/gameplay license.
 * Server exact BFS validation is mandatory before attaching boards to a
 * native source production request; an edit immediately invalidates approval.
 */
import React from 'react';
import {
  ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';

import { authHeaders } from '../auth/gameforgeAuth';
import { API_BASE } from '../../utils/apiBase';

const API = (API_BASE || '').replace(/\/$/, '');
const ENDPOINT = API + '/api/dragon-academy/native/production/puzzle';
const WIDTH = 12;
const HEIGHT = 10;
const TOOLS = [
  { token: '#', label: 'Wall' },
  { token: '.', label: 'Floor' },
  { token: '@', label: 'Hero' },
  { token: '$', label: 'Crate' },
  { token: 'o', label: 'Goal' },
] as const;

type Validation = {
  ok: boolean;
  digest: string;
  total_stages: number;
  stages: Array<{
    stage: number; layout_sha256: string;
    shortest_moves: number; solver_states: number; crates: number;
  }>;
};

type Props = {
  enabled: boolean;
  stages: number;
  onApprovedLevels: (levels: string[][] | null) => void;
};

function boundedBoard(value: unknown): value is string[] {
  return Array.isArray(value) && value.length === HEIGHT &&
    value.every(row => typeof row === 'string' &&
      row.length === WIDTH && /^[#.@$o]{12}$/.test(row));
}

function newBoard(): string[] {
  return [
    '############',
    '#..........#',
    '#..........#',
    '#..........#',
    '#...@......#',
    '#....$.....#',
    '#....o.....#',
    '#..........#',
    '#..........#',
    '############',
  ];
}

export default function DragonOriginalPuzzleEditor({
  enabled, stages, onApprovedLevels,
}: Props) {
  const [boards, setBoards] = React.useState<string[][]>([]);
  const [current, setCurrent] = React.useState(0);
  const [tool, setTool] = React.useState<string>('#');
  const [busy, setBusy] = React.useState(false);
  const [validating, setValidating] = React.useState(false);
  const [status, setStatus] = React.useState('');
  const [validated, setValidated] = React.useState<Validation | null>(null);
  const fetchEpoch = React.useRef(0);

  React.useEffect(() => {
    if (!enabled) {
      onApprovedLevels(null);
      return;
    }
    let cancelled = false;
    const controller = new AbortController();
    const generation = ++fetchEpoch.current;
    onApprovedLevels(null);
    setValidated(null);
    setCurrent(0);
    setBoards([]);
    setStatus('');
    setBusy(true);
    void (async () => {
      try {
        const response = await fetch(
          ENDPOINT + '/starter?stages=' + encodeURIComponent(stages), {
            headers: authHeaders(), signal: controller.signal, cache: 'no-store',
          },
        );
        if (!response.ok) throw new Error('Original starter layout request was rejected.');
        const result = await response.json() as {
          ok: boolean; levels: unknown; level_count: number;
        };
        if (!result.ok || !Array.isArray(result.levels) ||
            result.level_count !== stages || result.levels.length !== stages ||
            !result.levels.every(boundedBoard)) {
          throw new Error('Original puzzle starter grid did not meet safety bounds.');
        }
        if (!cancelled && fetchEpoch.current === generation) {
          setBoards((result.levels as string[][]).map(board => [...board]));
        }
      } catch {
        if (!cancelled && fetchEpoch.current === generation) {
          // Useful local original starter for offline editing. This fallback
          // is NOT treated as approved or certified and cannot be exported
          // without a separate backend validation.
          setBoards(Array.from({ length: stages }, () => newBoard()));
          setStatus('Could not load distinct starter stages. Edit offline and validate before export.');
        }
      } finally {
        if (!cancelled && fetchEpoch.current === generation) setBusy(false);
      }
    })();
    return () => { cancelled = true; controller.abort(); };
  }, [enabled, stages, onApprovedLevels]);

  if (!enabled) return null;

  const applyTool = (x: number, y: number) => {
    if (busy || validating || !boards[current]) return;
    const next = boards.map(board => [...board]);
    const selected = next[current];
    if (!selected[y] || x < 0 || x >= WIDTH) return;
    const before = selected[y][x];
    if (tool === '@' && before !== '@') {
      // Exactly one avatar on each grid: remove prior hero first.
      for (let row = 0; row < HEIGHT; row++) {
        selected[row] = selected[row].replace('@', '.');
      }
    }
    const copy = selected[y].split('');
    copy[x] = before === tool && tool !== '@' ? '.' : tool;
    selected[y] = copy.join('');
    setBoards(next);
    setValidated(null);
    setStatus('');
    onApprovedLevels(null);
  };

  const validate = async () => {
    if (busy || validating || boards.length !== stages ||
        !boards.every(boundedBoard)) return;
    setValidating(true);
    setValidated(null);
    setStatus('');
    onApprovedLevels(null);
    const generation = ++fetchEpoch.current;
    try {
      const response = await fetch(ENDPOINT + '/validate', {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        cache: 'no-store',
        body: JSON.stringify({ levels: boards }),
      });
      if (!response.ok) {
        throw new Error('Some boards are invalid, unsolvable or repeated. Check player, crates and goals.');
      }
      const result = await response.json() as Validation;
      if (!result.ok || result.total_stages !== stages ||
          !/^[a-f0-9]{64}$/.test(result.digest) ||
          !Array.isArray(result.stages) ||
          result.stages.length !== stages ||
          result.stages.some(row => row.shortest_moves < 1 ||
            row.shortest_moves > 400 || row.crates < 1 || row.crates > 3)) {
        throw new Error('Puzzle validation returned incomplete evidence.');
      }
      if (fetchEpoch.current === generation) {
        setValidated(result);
        onApprovedLevels(boards.map(board => [...board]));
        setStatus('All original puzzles solved exactly and approved for source generation.');
      }
    } catch (error) {
      if (fetchEpoch.current === generation) {
        setStatus(error instanceof Error ? error.message : 'Original level validation failed.');
      }
    } finally {
      if (fetchEpoch.current === generation) setValidating(false);
    }
  };

  const active = boards[current] || newBoard();

  return (
    <View style={styles.frame}>
      <Text style={styles.heading}>Original puzzle board editor</Text>
      <Text style={styles.help}>
        Paint the actual native 12×10 world. Each level requires exactly
        one hero, one to three crates, matching goals and a reachable solution.
        Dragon's exact solver checks your design before game source export.
      </Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.toolbar}>
        {TOOLS.map(option => (
          <TouchableOpacity key={option.token} accessibilityRole="button"
            accessibilityState={{ selected: option.token === tool }}
            disabled={busy || validating} onPress={() => setTool(option.token)}
            style={[styles.tool, option.token === tool && styles.selected]}>
            <Text style={styles.toolText}>{option.token} {option.label}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>
      <ScrollView horizontal showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.toolbar}>
        {boards.map((_, index) => (
          <TouchableOpacity key={index} accessibilityRole="button"
            accessibilityState={{ selected: index === current }}
            onPress={() => setCurrent(index)}
            style={[styles.tool, index === current && styles.selected]}>
            <Text style={styles.toolText}>Stage {index + 1}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>
      {busy && <ActivityIndicator color="#8fd2b2" />}
      <View style={styles.board}>
        {active.map((line, y) => (
          <View key={y} style={styles.row}>
            {line.split('').map((cell, x) => (
              <TouchableOpacity key={x}
                accessibilityRole="button"
                accessibilityLabel={'Stage ' + (current + 1) + ' row ' + (y + 1) +
                  ' column ' + (x + 1) + ': ' + cell}
                disabled={busy || validating}
                onPress={() => applyTool(x, y)}
                style={[styles.cell,
                  cell === '#' ? styles.wall :
                  cell === '@' ? styles.player :
                  cell === '$' ? styles.crate :
                  cell === 'o' ? styles.goal : styles.floor,
                ]}>
                <Text style={styles.cellText}>{cell === '.' ? ' ' : cell}</Text>
              </TouchableOpacity>
            ))}
          </View>
        ))}
      </View>
      <Text style={styles.help}>
        Grid data only—no scripts, commercial maps or third-party characters.
        Changing a cell immediately revokes its previous validation.
      </Text>
      <TouchableOpacity accessibilityRole="button" disabled={busy || validating}
        style={[styles.action, (busy || validating) && styles.disabled]}
        onPress={validate}>
        <Text style={styles.actionText}>
          {validating ? 'Solving original board…' : 'Validate and approve all stages'}
        </Text>
      </TouchableOpacity>
      {validated && (
        <View style={styles.results}>
          <Text style={styles.accepted}>All {validated.total_stages} stages have verified solutions</Text>
          {validated.stages.map(stage => (
            <Text key={stage.stage} style={styles.help}>
              Stage {stage.stage}: {stage.shortest_moves} optimal moves
              {' · '}{stage.crates} crates · {stage.solver_states} search states
            </Text>
          ))}
        </View>
      )}
      {!!status && <Text accessibilityRole="alert"
        style={validated ? styles.accepted : styles.warning}>{status}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  frame: { backgroundColor: '#122b32', padding: 14, borderRadius: 14, gap: 12 },
  heading: { fontSize: 18, color: '#e9fff5', fontWeight: '800' },
  help: { fontSize: 12, lineHeight: 20, color: '#b1cac6' },
  toolbar: { flexDirection: 'row', gap: 8 },
  tool: { borderRadius: 9, backgroundColor: '#27444b',
    paddingHorizontal: 11, paddingVertical: 9 },
  selected: { backgroundColor: '#477b61' },
  toolText: { color: '#e4ffef', fontSize: 13 },
  board: { backgroundColor: '#122027', alignSelf: 'center', padding: 5, gap: 0 },
  row: { flexDirection: 'row', justifyContent: 'center' },
  cell: { width: 23, height: 23, alignItems: 'center',
    justifyContent: 'center', borderWidth: 0.4, borderColor: '#29434b' },
  wall: { backgroundColor: '#566d75' },
  floor: { backgroundColor: '#1b3038' },
  player: { backgroundColor: '#36867b' },
  crate: { backgroundColor: '#bc7740' },
  goal: { backgroundColor: '#527eac' },
  cellText: { color: '#fff', fontWeight: '800', fontSize: 12 },
  action: { padding: 13, backgroundColor: '#336d52',
    borderRadius: 11, alignItems: 'center' },
  actionText: { fontWeight: '700', color: '#fff' },
  disabled: { opacity: 0.5 },
  results: { padding: 9, borderRadius: 10, backgroundColor: '#1d3b3f', gap: 5 },
  accepted: { color: '#b4edce', fontSize: 13, lineHeight: 19 },
  warning: { color: '#f5b1a9', fontSize: 13, lineHeight: 19 },
});
