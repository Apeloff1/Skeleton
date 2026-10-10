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
  ActivityIndicator, Platform, ScrollView, StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';

import * as DocumentPicker from 'expo-document-picker';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import { authHeaders } from '../auth/gameforgeAuth';
import { API_BASE } from '../../utils/apiBase';
import {
  parseNativeBoard, stepNativePreview, visibleNativeBoard,
  type EditorPreviewState, type PuzzleMove,
} from '../product/dragonPuzzlePreview';
import {
  type PuzzleHistory, initializePuzzleHistory, paintOriginalCell,
  undoPuzzleEdit, redoPuzzleEdit, canUndoPuzzle, canRedoPuzzle,
  reorderPuzzleStage,
  type DrawTile,
} from '../product/dragonPuzzleHistory';

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
    shortest_moves: number; shortest_solution: string; solver_states: number; crates: number;
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
  const [editHistory, setEditHistory] = React.useState<PuzzleHistory | null>(null);
  const [current, setCurrent] = React.useState(0);
  const [tool, setTool] = React.useState<string>('#');
  const [busy, setBusy] = React.useState(false);
  const [validating, setValidating] = React.useState(false);
  const [status, setStatus] = React.useState('');
  const [validated, setValidated] = React.useState<Validation | null>(null);
  const [play, setPlay] = React.useState<EditorPreviewState | null>(null);
  const [demoCursor, setDemoCursor] = React.useState(-1);
  const fetchEpoch = React.useRef(0);
  const hintEpoch = React.useRef(0);
  const [liveHint, setLiveHint] = React.useState('');
  const [hintBusy, setHintBusy] = React.useState(false);

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
    setPlay(null);
    setDemoCursor(-1);
    hintEpoch.current += 1;
    setLiveHint('');
    setHintBusy(false);
    setCurrent(0);
    setBoards([]);
    setEditHistory(null);
    setLiveHint('');
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
          const first=(result.levels as string[][]).map(board => [...board]);
          setBoards(first);
          setEditHistory(initializePuzzleHistory(first));
        }
      } catch {
        if (!cancelled && fetchEpoch.current === generation) {
          // Useful local original starter for offline editing. This fallback
          // is NOT treated as approved or certified and cannot be exported
          // without a separate backend validation.
          const first=Array.from({ length: stages }, () => newBoard());
          setBoards(first);
          setEditHistory(initializePuzzleHistory(first));
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
    if (busy || validating || play || !boards[current]) return;
    if (!editHistory) return;
    try {
      const update=paintOriginalCell(editHistory,current,x,y,tool as DrawTile);
      if (update===editHistory) return;
      setEditHistory(update);
      setBoards(update.current.boards.map(board => [...board]));
    } catch {
      setStatus('Native game board edit exceeds canvas bounds.');
      return;
    }
    setValidated(null);
    setPlay(null);
    setDemoCursor(-1);
    hintEpoch.current += 1;
    setLiveHint('');
    setStatus('');
    onApprovedLevels(null);
  };

  const rewindBoard = (redo: boolean) => {
    if (!editHistory || busy || validating || play) return;
    const updated=redo?redoPuzzleEdit(editHistory):undoPuzzleEdit(editHistory);
    if (updated===editHistory) return;
    setEditHistory(updated);
    setBoards(updated.current.boards.map(board => [...board]));
    setCurrent(updated.current.stage);
    setValidated(null);
    setDemoCursor(-1);
    hintEpoch.current += 1;
    setLiveHint('');
    setStatus('Board paint history changed. Validate the campaign before native export.');
    onApprovedLevels(null);
  };

  const moveStage = (direction: -1 | 1) => {
    if (!editHistory || busy || validating || play) return;
    const destination = current + direction;
    if (destination < 0 || destination >= boards.length) return;
    try {
      const update = reorderPuzzleStage(editHistory, current, destination);
      setEditHistory(update);
      setBoards(update.current.boards.map(stage => [...stage]));
      setCurrent(destination);
      setValidated(null);
      setDemoCursor(-1);
      hintEpoch.current += 1;
      setLiveHint('');
      setStatus('Game stage order changed. Revalidate the campaign before source export.');
      onApprovedLevels(null);
    } catch {
      setStatus('Could not reorder original game stages.');
    }
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
            row.shortest_moves > 400 || row.crates < 1 || row.crates > 3 ||
            typeof row.shortest_solution !== 'string' ||
            !/^[wasd]{1,400}$/.test(row.shortest_solution) ||
            row.shortest_solution.length !== row.shortest_moves)) {
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

  const loadOriginalPack = async () => {
    if (busy || validating) return;
    setStatus('');
    try {
      const picked = await DocumentPicker.getDocumentAsync({
        type: ['application/json', 'text/plain'],
        copyToCacheDirectory: true,
        multiple: false,
      });
      if (picked.canceled || !picked.assets?.length) return;
      const file = picked.assets[0];
      if (typeof file.size !== 'number' || file.size < 20 || file.size > 8192) {
        throw new Error('Original game level pack must be at most 8 KiB.');
      }
      let data: string;
      if (Platform.OS === 'web' && file.file) {
        data = await file.file.text();
      } else {
        data = await FileSystem.readAsStringAsync(file.uri, {
          encoding: FileSystem.EncodingType.UTF8,
        });
      }
      if (data.length > 8192) throw new Error('Original level pack too large.');
      const parsed = JSON.parse(data) as {
        schema?: unknown; levels?: unknown; level_count?: unknown;
      };
      if (parsed?.schema !== 'skeleton.ai.dragon.original_puzzle_level_pack.v1' ||
          !Array.isArray(parsed.levels) || parsed.level_count !== stages ||
          parsed.levels.length !== stages || !parsed.levels.every(boundedBoard)) {
        throw new Error('Imported original map does not match this campaign size.');
      }
      const rows = (parsed.levels as string[][]).map(grid => [...grid]);
      setBoards(rows);
      hintEpoch.current += 1;
      setLiveHint('');
      setEditHistory(initializePuzzleHistory(rows));
      setPlay(null);
      setDemoCursor(-1);
      setValidated(null);
      setCurrent(0);
      onApprovedLevels(null);
      setStatus('Level pack loaded. Run exact solver validation before exporting.');
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Original map import failed.');
    }
  };

  const saveOriginalPack = async () => {
    if (!validated || validated.total_stages !== boards.length ||
        !/^[a-f0-9]{64}$/.test(validated.digest)) return;
    const packDocument = {
      schema: 'skeleton.ai.dragon.original_puzzle_level_pack.v1',
      level_count: boards.length,
      levels: boards,
      digest: validated.digest,
      claim: 'source-only original authored grids, proved solvable, not legally cleared',
    };
    const raw = JSON.stringify(packDocument, null, 2) + '\n';
    if (raw.length > 8192) {
      setStatus('Level pack exceeds local game design archive limit.');
      return;
    }
    const name = 'dragon-original-levels-' + validated.digest.slice(0, 16) + '.json';
    try {
      if (Platform.OS === 'web') {
        const url = URL.createObjectURL(new Blob([raw], { type: 'application/json' }));
        try {
          const anchor = document.createElement('a');
          anchor.href = url; anchor.download = name;
          document.body.appendChild(anchor);
          anchor.click(); anchor.remove();
        } finally {
          setTimeout(() => URL.revokeObjectURL(url), 15_000);
        }
      } else {
        if (!FileSystem.documentDirectory) {
          throw new Error('Local original game file storage unavailable.');
        }
        const uri = FileSystem.documentDirectory + name;
        await FileSystem.writeAsStringAsync(uri, raw, {
          encoding: FileSystem.EncodingType.UTF8,
        });
        if (await Sharing.isAvailableAsync()) {
          await Sharing.shareAsync(uri, {
            mimeType: 'application/json',
            dialogTitle: 'Share original Dragon puzzle levels',
          });
        }
      }
      setStatus('Validated original game design saved. It can be imported again.');
    } catch {
      setStatus('Unable to export original level-pack JSON from this device.');
    }
  };

  const startGamePreview = () => {
    if (busy || validating) return;
    if (play) {
      hintEpoch.current += 1;
      setLiveHint('');
      setPlay(null);
      setDemoCursor(-1);
      setStatus('');
      return;
    }
    try {
      setDemoCursor(-1);
      hintEpoch.current += 1;
      setLiveHint('');
      setPlay(parseNativeBoard(boards[current]));
      setStatus('Local design playtest only. Exact solver validation remains required before export.');
    } catch {
      setStatus('Place one hero and matching crates/goals before local playtesting.');
    }
  };

  const movePlaytest = (action: PuzzleMove | 'undo' | 'reset') => {
    if (busy || validating || !play) return;
    try {
      hintEpoch.current += 1;
      setLiveHint('');
      setDemoCursor(-1);
      setPlay(stepNativePreview(play, action));
    }
    catch { setStatus('Original game preview rejected this move.'); }
  };

  const fetchCurrentHint = async () => {
    if (!play || hintBusy || busy || validating || !boards[current]) return;
    const generation = ++hintEpoch.current;
    setHintBusy(true);
    setLiveHint('');
    try {
      const response = await fetch(ENDPOINT + '/current-hint', {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        cache: 'no-store',
        body: JSON.stringify({
          rows: boards[current], player: play.player, crates: play.crates,
        }),
      });
      if (!response.ok) throw new Error('No bounded live route was proven from this game state.');
      const result = await response.json() as {
        ok: boolean; next_move: string | null;
        shortest_route: string; remaining_moves: number; solved: boolean;
      };
      if (!result.ok || typeof result.shortest_route !== 'string' ||
          !/^[wasd]{0,400}$/.test(result.shortest_route) ||
          result.shortest_route.length !== result.remaining_moves ||
          (result.solved ? result.next_move !== null :
            result.next_move !== result.shortest_route[0])) {
        throw new Error('Original current-state solver returned inconsistent gameplay proof.');
      }
      if (generation === hintEpoch.current) {
        setLiveHint(result.solved ? 'This original puzzle is already complete.' :
          'From this position: ' + result.remaining_moves + ' moves. Next: ' +
          ({w:'↑',a:'←',s:'↓',d:'→'} as Record<string,string>)[result.next_move!]);
      }
    } catch (error) {
      if (generation === hintEpoch.current) {
        setLiveHint(error instanceof Error ? error.message : 'Live current-position hint failed.');
      }
    } finally {
      if (generation === hintEpoch.current) setHintBusy(false);
    }
  };

  const walkthrough = validated?.stages[current]?.shortest_solution ?? '';
  const beginWalkthrough = () => {
    if (busy || validating || !validated || !boards[current] || !walkthrough) return;
    try {
      hintEpoch.current += 1;
      setLiveHint('');
      setPlay(parseNativeBoard(boards[current]));
      setDemoCursor(0);
      setStatus('Follow the independently solved shortest route, one actual game move at a time.');
    } catch {
      setStatus('The original game board could not be replayed.');
    }
  };

  const stepWalkthrough = () => {
    if (!play || demoCursor < 0 || demoCursor >= walkthrough.length) return;
    const next = stepNativePreview(play, walkthrough[demoCursor] as PuzzleMove);
    // The backend shortest-path proof must make a real valid movement at
    // every step. If a grid changed or a client replay diverges, stop.
    if (next.moves !== play.moves + 1) {
      setDemoCursor(-1);
      setStatus('The optimal walkthrough diverged. Revalidate this board.');
      return;
    }
    hintEpoch.current += 1;
    setLiveHint('');
    setPlay(next);
    setDemoCursor(demoCursor + 1);
    if (demoCursor + 1 === walkthrough.length) {
      if (!next.completed) {
        setDemoCursor(-1);
        setStatus('The original level proof did not complete in this preview.');
      } else {
        setStatus('Shortest original route completed in ' + next.moves + ' real moves.');
      }
    }
  };

  const active = play ? visibleNativeBoard(play) : boards[current] || newBoard();

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
            disabled={busy || validating || !!play} onPress={() => setTool(option.token)}
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
            onPress={() => {
              hintEpoch.current += 1; setLiveHint('');
              setCurrent(index); setPlay(null); setDemoCursor(-1);
            }}
            style={[styles.tool, index === current && styles.selected]}>
            <Text style={styles.toolText}>Stage {index + 1}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>
      <View style={styles.fileActions}>
        <TouchableOpacity accessibilityRole="button"
          accessibilityLabel="Undo original game board paint"
          disabled={!editHistory || !canUndoPuzzle(editHistory) || busy || validating || !!play}
          onPress={() => rewindBoard(false)}
          style={[styles.fileButton, (!editHistory || !canUndoPuzzle(editHistory) ||
            busy || validating || !!play) && styles.disabled]}>
          <Text style={styles.actionText}>↶ Undo painting</Text>
        </TouchableOpacity>
        <TouchableOpacity accessibilityRole="button"
          accessibilityLabel="Redo original game board paint"
          disabled={!editHistory || !canRedoPuzzle(editHistory) || busy || validating || !!play}
          onPress={() => rewindBoard(true)}
          style={[styles.fileButton, (!editHistory || !canRedoPuzzle(editHistory) ||
            busy || validating || !!play) && styles.disabled]}>
          <Text style={styles.actionText}>↷ Redo painting</Text>
        </TouchableOpacity>
        {editHistory && <Text style={styles.help}>
          {editHistory.previous.length} undo steps · {editHistory.next.length} redo steps
        </Text>}
      </View>
      {boards.length > 1 && (
        <View style={styles.fileActions}>
          <TouchableOpacity accessibilityRole="button"
            accessibilityLabel={'Move original stage ' + (current + 1) + ' earlier'}
            disabled={!editHistory || busy || validating || !!play || current === 0}
            onPress={() => moveStage(-1)}
            style={[styles.fileButton, (current === 0 || busy || validating || !!play) && styles.disabled]}>
            <Text style={styles.actionText}>Move stage earlier</Text>
          </TouchableOpacity>
          <TouchableOpacity accessibilityRole="button"
            accessibilityLabel={'Move original stage ' + (current + 1) + ' later'}
            disabled={!editHistory || busy || validating || !!play || current === boards.length - 1}
            onPress={() => moveStage(1)}
            style={[styles.fileButton, (current === boards.length - 1 || busy || validating || !!play) && styles.disabled]}>
            <Text style={styles.actionText}>Move stage later</Text>
          </TouchableOpacity>
        </View>
      )}
      {busy && <ActivityIndicator color="#8fd2b2" />}
      <View style={styles.board}>
        {active.map((line, y) => (
          <View key={y} style={styles.row}>
            {line.split('').map((cell, x) => (
              <TouchableOpacity key={x}
                accessibilityRole="button"
                accessibilityLabel={'Stage ' + (current + 1) + ' row ' + (y + 1) +
                  ' column ' + (x + 1) + ': ' + cell}
                disabled={busy || validating || !!play}
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
      <TouchableOpacity accessibilityRole="button"
        disabled={busy || validating || !boards[current]}
        style={[styles.fileButton, { alignSelf: 'flex-start' },
          (busy || validating) && styles.disabled]}
        onPress={startGamePreview}>
        <Text style={styles.actionText}>
          {play ? 'Exit local game playtest' : 'Play-test my original game board'}
        </Text>
      </TouchableOpacity>
      {validated && !!walkthrough && (
        <TouchableOpacity accessibilityRole="button"
          disabled={busy || validating}
          onPress={beginWalkthrough} style={styles.fileButton}>
          <Text style={styles.actionText}>
            Replay exact shortest solution — Stage {current + 1} ({walkthrough.length} moves)
          </Text>
        </TouchableOpacity>
      )}
      {play && demoCursor >= 0 && (
        <View style={styles.results}>
          <Text style={styles.accepted}>
            Optimal walkthrough {demoCursor}/{walkthrough.length} moves
            {demoCursor < walkthrough.length
              ? ' · Next: ' + ({w:'↑',a:'←',s:'↓',d:'→'} as Record<string,string>)[walkthrough[demoCursor]]
              : ' · Solved'}
          </Text>
          <TouchableOpacity accessibilityRole="button"
            disabled={demoCursor >= walkthrough.length}
            onPress={stepWalkthrough} style={styles.fileButton}>
            <Text style={styles.actionText}>Advance one proven move</Text>
          </TouchableOpacity>
        </View>
      )}
      {play && (
        <View style={styles.results}>
          <Text style={play.completed ? styles.accepted : styles.help}>
            {play.completed ? 'Puzzle completed!' : 'Original game in progress'}
            {' · '}Moves: {play.moves} · Pushes: {play.pushes}
          </Text>
          <TouchableOpacity accessibilityRole="button"
            accessibilityLabel="Ask Dragon for an exact hint from current puzzle position"
            disabled={hintBusy || busy || validating}
            onPress={fetchCurrentHint} style={styles.fileButton}>
            <Text style={styles.actionText}>
              {hintBusy ? 'Solving current game position…' : 'Get shortest hint from here'}
            </Text>
          </TouchableOpacity>
          {!!liveHint && <Text style={styles.accepted}>{liveHint}</Text>}
          <View style={styles.fileActions}>
            {([
              ['← Left', 'a'], ['↑ Up', 'w'],
              ['↓ Down', 's'], ['→ Right', 'd'],
              ['Undo', 'undo'], ['Reset', 'reset'],
            ] as const).map(([label, action]) => (
              <TouchableOpacity key={action} accessibilityRole="button"
                accessibilityLabel={'Original game ' + label}
                onPress={() => movePlaytest(action)}
                style={styles.fileButton}>
                <Text style={styles.actionText}>{label}</Text>
              </TouchableOpacity>
            ))}
          </View>
          <Text style={styles.help}>
            This local test runs actual Sokoban movement rules but is not a
            compiled binary. Native gameplay testing is separate.
          </Text>
        </View>
      )}
      <Text style={styles.help}>
        Grid data only—no scripts, commercial maps or third-party characters.
        Changing a cell immediately revokes its previous validation.
      </Text>
      <View style={styles.fileActions}>
        <TouchableOpacity accessibilityRole="button" disabled={busy || validating}
          style={[styles.fileButton, (busy || validating) && styles.disabled]}
          onPress={loadOriginalPack}>
          <Text style={styles.actionText}>Import original level JSON</Text>
        </TouchableOpacity>
        <TouchableOpacity accessibilityRole="button"
          disabled={busy || validating || !validated}
          style={[styles.fileButton, !validated && styles.disabled]}
          onPress={saveOriginalPack}>
          <Text style={styles.actionText}>Save approved level JSON</Text>
        </TouchableOpacity>
      </View>
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
  fileActions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  fileButton: { padding: 10, borderRadius: 9, backgroundColor: '#284e5c' },
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
