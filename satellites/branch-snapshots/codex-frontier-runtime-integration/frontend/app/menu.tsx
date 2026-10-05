/**
 * /menu — the "everything that's in the APK" home.
 *
 * Surfaces every modal feature available in the app as a tappable card,
 * organised by category. Tapping a card sets the global modalStore to the
 * target feature and navigates to the code editor home where the modal
 * actually renders.
 *
 * This is the route users land on after install — it gives them a true
 * "see everything" experience instead of being dropped straight into the
 * code editor with features hidden behind a small overflow button.
 */
import { NATIVE_DRIVER } from '../src/utils/platformStyles';
import { useMemo, useRef, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, Pressable, RefreshControl,
  Animated as RNAnimated, Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import { useModalStore, ModalType } from '../store/modalStore';
import theme from '../theme/tokens';
import { Screen, AppHeader, SearchBar, Chip, FeatureCard, SectionHeader } from '../components/ui';
import { useNotesCount } from '../utils/useNotesCount';
import * as haptics from '../utils/haptics';
import { toast } from '../components/Toast';
import { actionSheet } from '../components/ActionSheet';
import { useMenuPrefs, togglePin, toggleHide } from '../utils/menuPrefs';
import { useFeatureFlag } from '../utils/featureFlags';

// ─────────────────────────────────────────────────────────────────────
// FEATURE CATALOG — single source of truth for what the APK contains.
// Add an entry here whenever a new modal lands in index.tsx.
// ─────────────────────────────────────────────────────────────────────
interface FeatureCardItem {
  id: ModalType | string;
  title: string;
  desc: string;
  icon: string;
  color: string;
  /** If true, the card navigates to a /route instead of opening a modal. */
  route?: string;
  /** Sort key — higher = more prominent. */
  hot?: boolean;
}

const CATEGORIES: { name: string; icon: string; color: string; cards: FeatureCardItem[] }[] = [
  {
    name: 'Learn',
    icon: 'school',
    color: '#F59E0B',
    cards: [
      { id: 'my-classes', title: 'My Classes', desc: '10 CS classes · 15 weeks each · labs, glossary, quizzes', icon: 'school', color: '#F59E0B', route: '/my-classes', hot: true },
      { id: 'class-week', title: 'Class Week Detail', desc: 'Read · Lab · Practice tabs per week', icon: 'book', color: '#F59E0B', route: '/class-week' },
      { id: 'readingLibrary', title: 'Reading Library', desc: '300+ books · glossary · comprehension', icon: 'library', color: '#A78BFA', route: '/readingLibrary', hot: true },
      { id: 'readingCorner', title: 'Reading Corner', desc: 'Focused reader with TTS audiobook', icon: 'book-outline', color: '#A78BFA', route: '/reading-corner' },
      { id: 'megaAcademy', title: 'Mega Academy', desc: 'Cross-discipline curriculum hub', icon: 'school-outline', color: '#F59E0B', route: '/mega-academy', hot: true },
      { id: 'csAcademy', title: 'CS Academy', desc: 'Computer Science deep-dive', icon: 'desktop', color: '#3B82F6', route: '/cs-academy' },
      { id: 'mathAcademyFull', title: 'Math Academy', desc: 'Calculus, linear algebra, discrete math', icon: 'calculator', color: '#10B981', route: '/math-academy' },
      { id: 'physicsAcademy', title: 'Physics Academy', desc: 'Mechanics, EM, quantum', icon: 'planet-outline', color: '#A78BFA', route: '/physics-academy' },
      { id: 'languageAcademy', title: 'Language Academy', desc: '20+ programming languages', icon: 'code-slash', color: '#8B5CF6', route: '/language-academy' },
      { id: 'languageTrack', title: 'Language Track', desc: 'Structured language curriculum', icon: 'git-branch', color: '#8B5CF6', route: '/language-track' },
      { id: 'masterclass', title: 'Masterclass', desc: 'Long-form expert lessons', icon: 'ribbon', color: '#F59E0B', route: '/masterclass' },
      { id: 'studyPaths', title: 'Study Paths', desc: 'Curated learning journeys', icon: 'map', color: '#3B82F6', route: '/study-paths' },
      { id: 'education', title: 'Education Hub', desc: 'Tutorials and tutoring', icon: 'school', color: '#F59E0B', route: '/education' },
      { id: 'learningHub', title: 'Learning Hub', desc: 'Browse all learning resources', icon: 'apps', color: '#3B82F6', route: '/learning-hub' },
      { id: 'immersiveLearning', title: 'Immersive Learning', desc: 'Interactive deep-dives', icon: 'eye', color: '#A78BFA', route: '/immersive-learning' },
      { id: 'immersiveTutor', title: 'Immersive Tutor', desc: 'AI-led private tutoring', icon: 'person', color: '#3B82F6', route: '/immersive-tutor' },
      { id: 'knowledgeDatabases', title: 'Knowledge Databases', desc: 'Searchable reference dumps', icon: 'server', color: '#10B981', route: '/knowledge-databases' },
      { id: 'curriculum', title: 'Curriculum Browser', desc: 'Drill into syllabus', icon: 'list', color: '#F59E0B', route: '/curriculum' },
      { id: 'flashcards', title: 'Flashcards', desc: 'Spaced-repetition review', icon: 'card', color: '#10B981', route: '/flashcards' },
      { id: 'interactiveQuizzes', title: 'Interactive Quizzes', desc: 'Practice tests with feedback', icon: 'help-circle', color: '#F59E0B', route: '/interactive-quizzes' },
      { id: 'dailyChallenges', title: 'Daily Challenges', desc: 'A new problem every day', icon: 'flame', color: '#EF4444', route: '/daily-challenges' },
      { id: 'challengeArena', title: 'Challenge Arena', desc: 'Compete on coding problems', icon: 'trophy', color: '#F59E0B', route: '/challenges' },
      { id: 'rosettaPlayground', title: 'Rosetta Playground', desc: 'Same task, every language', icon: 'language', color: '#8B5CF6', route: '/rosetta-playground', hot: true },
    ],
  },
  {
    name: 'Build',
    icon: 'build',
    color: '#10B981',
    cards: [
      { id: 'gameFactory', title: 'Galaxy Studio', desc: 'One flow: questionnaire → 100-phase build → snowball → APK', icon: 'planet', color: '#8B5CF6', hot: true, route: '/studio' },
      { id: 'gameFactoryClassic', title: 'Galaxy Studio Factory (Classic)', desc: 'The full questionnaire + 100-phase build modal', icon: 'planet-outline', color: '#8B5CF6', route: '/galaxy' },
      { id: 'aiGameGenerator', title: 'AI Game Generator', desc: 'Spec to playable in one prompt', icon: 'sparkles', color: '#8B5CF6', route: '/ai-game-generator' },
      { id: 'codeToApp', title: 'Code → App', desc: 'Scaffolds a full app from a snippet', icon: 'apps', color: '#3B82F6', route: '/code-to-app' },
      { id: 'codePlayground', title: 'Code Playground', desc: 'Multi-file sandbox · run any language', icon: 'flask', color: '#F59E0B', route: '/playground', hot: true },
      { id: 'assetPipeline', title: 'Asset Pipeline', desc: '2D sprites · 3D models · tilesets', icon: 'images', color: '#A78BFA', route: '/assets', hot: true },
      { id: 'musicPipeline', title: 'Music Pipeline', desc: 'Score · SFX · adaptive game music', icon: 'musical-notes', color: '#3B82F6', route: '/music', hot: true },
      { id: 'imagine', title: 'Imagine', desc: 'AI image generator · gpt-image-1 · Nano Banana', icon: 'image', color: '#8B5CF6', route: '/imagine', hot: true },
      { id: 'aiPipeline', title: 'AI Pipeline', desc: 'Chain LLM calls', icon: 'git-network', color: '#3B82F6', route: '/ai-pipeline' },
      { id: 'hybridPipeline', title: 'Hybrid Pipeline', desc: 'AI + tools + scripts', icon: 'git-merge', color: '#10B981', route: '/hybrid-pipeline' },
      { id: 'multiAgent', title: 'Multi-Agent', desc: 'Coordinate AI agents on a task', icon: 'people', color: '#A78BFA', route: '/agents', hot: true },
      { id: 'swarmPlanner', title: 'Swarm Planner', desc: 'Director→leads→platoons→workers task DAG · 100% coverage · deterministic', icon: 'git-network', color: '#7C9CFF', route: '/swarm-planner', hot: true },
      { id: 'commandCenter', title: 'Gamefile Command Center', desc: '⌘K palette → forge quests, items, enemies, lore & more from text · run the 14-gate AAA engine per gamefile', icon: 'terminal', color: '#7C9CFF', route: '/command-center', hot: true },
      { id: 'stageBuilder', title: 'Stage Builder', desc: 'Lay out the game spine — 63 distinct stage types (boss, cutscene, interlude…). Building a stage mints the first gamefiles', icon: 'layers', color: '#3B82F6', route: '/stages', hot: true },
      { id: 'itemFoundry', title: 'Item Foundry', desc: 'Every agent forges a full item — skin, code, placement — into gamefiles', icon: 'hammer', color: '#A78BFA', route: '/item-foundry', hot: true },
      { id: 'constructForge', title: 'Construct Forge', desc: 'Forge large buildings, cities & castles + materials in 3D · 504 presets/era · Vault mount', icon: 'business', color: '#6c8cff', route: '/construct-forge', hot: true },
      { id: 'forgeHub', title: 'Forge Hub', desc: '215 live forges in 3D — characters, npcs, creatures, plants, vehicles, weapons, world, FX & more · AI-enriched · Vault mount', icon: 'apps', color: '#34D399', route: '/forge-hub', hot: true },
      { id: 'netcode', title: 'Netcode Studio', desc: 'Generate multiplayer scaffolds · rollback · lockstep · authoritative', icon: 'wifi', color: '#3B82F6', route: '/multiplayer', hot: true },
      { id: 'trophy', title: 'Trophy Case', desc: 'Champion rewards earned across the arenas', icon: 'trophy', color: '#fbbf24', route: '/trophy-case' },
      { id: 'gallery', title: 'Build Gallery', desc: 'Past Galaxy Studio builds', icon: 'grid', color: '#8B5CF6', route: '/gallery' },
      { id: 'myBuilds', title: 'My Builds', desc: 'Auto-saved games · open, download zip, re-zip', icon: 'rocket', color: '#3B82F6', route: '/my-builds', hot: true },
      { id: 'agentCodex', title: 'Agent Codex', desc: '28 knowledge DBs · 614k rows · grounded agent context', icon: 'book', color: '#F59E0B', route: '/agentCodex', hot: true },
      { id: 'buildHub', title: 'Build · Code · AI Hub', desc: '16 services · Playground · Rosetta · SOTA · Imagine · Assets · Multi-Agent', icon: 'rocket', color: '#3B82F6', route: '/build-hub', hot: true },
    ],
  },
  {
    name: 'Code',
    icon: 'code-slash',
    color: '#3B82F6',
    cards: [
      { id: 'editor', title: 'Code Editor', desc: 'The Studio home (this is the editor)', icon: 'create', color: '#3B82F6', route: '/hub', hot: true },
      { id: 'compiler', title: 'Compiler Suite', desc: 'Run, debug, fix', icon: 'play', color: '#10B981', route: '/compiler' },
      { id: 'debugger', title: 'Debugger', desc: 'AI-driven bug analysis · 12 languages', icon: 'bug', color: '#EF4444', route: '/debugger', hot: true },
      { id: 'codeIntelligence', title: 'Code Intelligence', desc: 'Auto-doc · test-gen · migrate · architecture', icon: 'bulb', color: '#F5C451', route: '/intelligence', hot: true },
      { id: 'bugfixLibrary', title: 'Bugfix Library', desc: 'Common bugs + fixes', icon: 'medkit', color: '#EF4444', route: '/bugfix-library' },
      { id: 'referenceHub', title: 'Reference Hub', desc: 'API + syntax docs', icon: 'document-text', color: '#94A3B8', route: '/reference' },
      { id: 'liveCollab', title: 'Live Collaboration', desc: 'Code with Jeeves in real time', icon: 'people-circle', color: '#10B981', route: '/collab', hot: true },
      { id: 'collaboration', title: 'Collaboration Hub', desc: 'Async + sync collab', icon: 'people', color: '#10B981', route: '/collaboration' },
      { id: 'groupChat', title: 'Group Chat', desc: 'Team chat inside Studio', icon: 'chatbubbles', color: '#8B5CF6', route: '/group-chat' },
      { id: 'vault', title: 'Vault', desc: 'Saved projects + files', icon: 'file-tray-stacked', color: '#3B82F6', route: '/vault' },
      { id: 'language', title: 'Languages', desc: 'Switch active language', icon: 'language', color: '#8B5CF6', route: '/lang-recommend' },
    ],
  },
  {
    name: 'AI',
    icon: 'sparkles',
    color: '#A78BFA',
    cards: [
      { id: 'ai', title: 'AI Assistant', desc: 'GPT-4o powered chat', icon: 'sparkles', color: '#A78BFA', route: '/jeeves', hot: true },
      { id: 'aiSuggestions', title: 'AI Suggestions', desc: 'Context-aware tips', icon: 'bulb', color: '#F5C451', route: '/ai-suggestions' },
      { id: 'aiInteractionsLog', title: 'AI Interactions Log', desc: 'Every AI call, replayable', icon: 'time', color: '#94A3B8', route: '/ai-interactions' },
      { id: 'jeeves', title: 'Jeeves', desc: 'Your persistent AI butler', icon: 'chatbubble', color: '#8B5CF6', route: '/jeeves', hot: true },
      { id: 'jeevesEQ', title: 'Jeeves EQ', desc: 'Emotion-aware AI', icon: 'heart', color: '#8B5CF6', route: '/jeeves-eq' },
      { id: 'jeevesLevel', title: 'Jeeves Level', desc: 'Persona depth tuner', icon: 'pulse', color: '#A78BFA', route: '/jeeves-level' },
      { id: 'sota', title: 'SOTA Models', desc: 'Switch between latest LLMs', icon: 'flash', color: '#F5C451', route: '/sota' },
      { id: 'sotaExtended', title: 'SOTA Extended', desc: 'Specialist & fine-tuned models', icon: 'flash-outline', color: '#F5C451', route: '/sota-extended' },
      { id: 'multiAgent', title: 'Multi-Agent', desc: 'Coordinate AI agents on a task', icon: 'people', color: '#A78BFA', route: '/multi-agent' },
      { id: 'gameFactory', title: 'Game Factory', desc: 'Idea → playable in one prompt', icon: 'planet', color: '#8B5CF6', route: '/game-factory' },
    ],
  },
  {
    name: 'Tools',
    icon: 'construct',
    color: '#94A3B8',
    cards: [
      { id: 'telemetry', title: 'Telemetry & Security', desc: 'Modal logs · audit ring · rate limits · self-heal', icon: 'analytics-outline', color: '#3B82F6', route: '/telemetry', hot: true },
      { id: 'apkInspector', title: 'APK Inspector', desc: 'Verify your APK is installable on Android 7+', icon: 'shield-checkmark-outline', color: '#10B981', route: '/apk-inspector', hot: true },
      { id: 'toolsArena', title: 'Tools Arena', desc: '8 power tools · same surface agents use', icon: 'construct-outline', color: '#F59E0B', route: '/tools-arena', hot: true },
      { id: 'scheduler', title: 'Scheduler', desc: 'Calendar + reminders + Pomodoro', icon: 'calendar', color: '#10B981', route: '/scheduler', hot: true },
      { id: 'pomodoro', title: 'Pomodoro', desc: 'Focus timer', icon: 'timer', color: '#EF4444', route: '/pomodoro' },
      { id: 'notes', title: 'Sticky Notes', desc: 'Pinnable pastel scratchpad · auto-saved & searchable', icon: 'document-text', color: '#F5C451', route: '/notes', hot: true },
      { id: 'search', title: 'Search', desc: 'Find anything in the app', icon: 'search', color: '#3B82F6', route: '/search' },
      { id: 'hub', title: 'Ultimate Hub', desc: 'All features in one place', icon: 'apps', color: '#3B82F6', route: '/hub' },
      { id: 'advanced', title: 'Advanced Features', desc: 'Power user settings', icon: 'cog', color: '#94A3B8', route: '/advanced' },
      { id: 'offlineSync', title: 'Offline Sync', desc: 'Work without a network', icon: 'cloud-offline', color: '#10B981', route: '/offline-sync' },
      { id: 'thermalMonitor', title: 'Thermal Monitor', desc: 'Device health + throttle', icon: 'thermometer', color: '#EF4444', route: '/thermal' },
      { id: 'pipeline', title: 'Pipeline Visualizer', desc: 'See AI pipelines as a graph', icon: 'git-network', color: '#3B82F6', route: '/ai-pipeline' },
      { id: 'safeMode', title: 'Safe Mode', desc: 'Boot trace + crash recovery', icon: 'shield-half', color: '#F5C451', route: '/safe-mode' },
      { id: 'auditRoutes', title: 'Audit Routes', desc: `${83}+ routes · health check + deep-link map`, icon: 'list-circle', color: '#3B82F6', route: '/audit-routes' },
      { id: 'perf', title: 'Performance', desc: 'Slow-screen leaderboard · p95 mount latency', icon: 'speedometer', color: '#10B981', route: '/perf' },
    ],
  },
  {
    name: 'Progress',
    icon: 'trophy',
    color: '#F5C451',
    cards: [
      { id: 'dashboard', title: 'Dashboard', desc: 'Stats, streak, recent', icon: 'speedometer', color: '#3B82F6', route: '/dashboard', hot: true },
      { id: 'profile', title: 'Profile', desc: 'Your account', icon: 'person-circle', color: '#A78BFA', route: '/profile' },
      { id: 'myProgress', title: 'My Progress', desc: 'Per-class progress + certificates', icon: 'analytics', color: '#10B981', route: '/progress' },
      { id: 'achievements', title: 'Achievements', desc: 'Earned badges + milestones', icon: 'medal', color: '#F5C451', route: '/achievements' },
      { id: 'gamification', title: 'Gamification', desc: 'XP, levels, leaderboards', icon: 'game-controller', color: '#A78BFA', route: '/gamification' },
      { id: 'leaderboard', title: 'Leaderboard', desc: 'Top builders this week', icon: 'trophy', color: '#F5C451', route: '/leaderboard' },
      { id: 'certificate', title: 'Certificate', desc: 'Shareable completion certificate', icon: 'ribbon', color: '#10B981', route: '/certificate' },
    ],
  },
  {
    name: 'Settings',
    icon: 'settings',
    color: '#94A3B8',
    cards: [
      { id: 'settings-coding', title: 'Coding Settings', desc: 'Metronome, bracket-pair, AI explain', icon: 'musical-notes', color: '#3B82F6', route: '/settings/coding' },
      { id: 'settings-api', title: 'API Controller', desc: 'Live request stats + cache', icon: 'pulse', color: '#10B981', route: '/settings/api', hot: true },
      { id: 'settings-jeeves', title: 'Jeeves Settings', desc: 'Directives + persona tuning', icon: 'chatbubble-ellipses', color: '#8B5CF6', route: '/settings/jeeves' },
      { id: 'settings-academy', title: 'Academy Settings', desc: 'Reader preferences', icon: 'school', color: '#F59E0B', route: '/settings/academy' },
      { id: 'settings-galaxy', title: 'Galaxy Studio Settings', desc: 'Build pipeline weights', icon: 'planet', color: '#8B5CF6', route: '/settings/galaxy-studio' },
      { id: 'settings-offline', title: 'Offline Settings', desc: 'Cache controls', icon: 'cloud-offline', color: '#10B981', route: '/settings/offline' },
      { id: 'settings', title: 'All Settings', desc: 'Index of every preference', icon: 'settings', color: '#94A3B8', route: '/settings' },
    ],
  },
];

export default function MenuScreen() {
  const router = useRouter();
  const openModal = useModalStore(s => s.openModal);
  /** Deep-link `?showHidden=true` flips the catalog into "only hidden cards" mode
   *  so users can find what they hid from Settings → Customised. */
  const params = useLocalSearchParams<{ showHidden?: string }>();
  const showHiddenOnly = String(params?.showHidden || '').toLowerCase() === 'true';
  const [query, setQuery] = useState('');
  const [activeCat, setActiveCat] = useState<string | null>(null);
  /** Live count of saved sticky notes — surfaced on the Tools section header. */
  const notesCount = useNotesCount();
  /** Persistent pinned / hidden feature ids — drives long-press curation. */
  const menuPrefs = useMenuPrefs();
  /** Reactive feature flag subscriptions for live gating. */
  const flagCollab     = useFeatureFlag('experimental_collab');
  const flagRouteAudit = useFeatureFlag('show_route_audit');

  // ── Scroll-to-top FAB + pull-to-refresh comfort ────────────────────
  const scrollRef = useRef<ScrollView | null>(null);
  const fabOpacity = useRef(new RNAnimated.Value(0)).current;
  const [showFab,   setShowFab]   = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const onScroll = (e: any) => {
    const y = e?.nativeEvent?.contentOffset?.y ?? 0;
    const next = y > 600;
    if (next !== showFab) {
      setShowFab(next);
      RNAnimated.timing(fabOpacity, {
        toValue: next ? 1 : 0,
        duration: 180,
        useNativeDriver: NATIVE_DRIVER,
      }).start();
    }
  };

  const scrollToTop = useCallback(() => {
    haptics.tap();
    scrollRef.current?.scrollTo({ y: 0, animated: true });
  }, []);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    haptics.tap();
    setTimeout(() => {
      setRefreshing(false);
      toast.info('Catalog refreshed');
    }, 400);
  }, []);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    // Card IDs that are flag-gated. Each entry is { id, enabled }.
    const flagGate = (id: string): boolean => {
      if (id === 'liveCollab' || id === 'collaboration') return flagCollab;
      if (id === 'auditRoutes') return flagRouteAudit;
      return true;
    };
    return CATEGORIES
      .filter(c => !activeCat || c.name === activeCat)
      .map(c => ({
        ...c,
        cards: c.cards
          // Drop cards that a feature flag has disabled.
          .filter(f => flagGate(f.id as string))
          // Hide user-hidden cards
          .filter(f => !menuPrefs.hidden.includes(f.id))
          // Apply free-text filter
          .filter(f =>
            !q ||
            f.title.toLowerCase().includes(q) ||
            f.desc.toLowerCase().includes(q)
          )
          // Pinned cards bubble to top of their category
          .sort((a, b) => {
            const ap = menuPrefs.pinned.includes(a.id) ? 0 : 1;
            const bp = menuPrefs.pinned.includes(b.id) ? 0 : 1;
            return ap - bp;
          }),
      }))
      .filter(c => c.cards.length > 0);
  }, [query, activeCat, menuPrefs, flagCollab, flagRouteAudit]);

  const totalCount = useMemo(
    () => CATEGORIES.reduce((sum, c) => sum + c.cards.length, 0),
    [],
  );

  const onTap = (card: FeatureCardItem) => {
    if (card.route) {
      router.push(card.route as any);
      return;
    }
    // Set global modal target then navigate to the editor where the modal renders.
    openModal(card.id as ModalType);
    router.push('/' as any);
  };

  /** Long-press a feature card → curate menu (Open / About / Pin / Hide). */
  const showCardSheet = (card: FeatureCardItem) => {
    const pinned = menuPrefs.pinned.includes(card.id);
    actionSheet.show({
      title: card.title,
      message: card.desc,
      options: [
        { label: 'Open',          kind: 'primary', onPress: () => onTap(card) },
        { label: pinned ? 'Unpin from top' : 'Pin to top of category',
          onPress: async () => {
            const nowPinned = await togglePin(card.id);
            toast.success(nowPinned ? `${card.title} pinned` : `${card.title} unpinned`);
          },
        },
        { label: `About · ID: ${card.id}`,
          onPress: () => toast.info(`${card.title} · category lookup → ${card.desc}`, { durationMs: 4500 }),
        },
        { label: 'Hide from menu', kind: 'destructive',
          onPress: async () => {
            await toggleHide(card.id);
            toast.warn(`${card.title} hidden`, {
              durationMs: 5000,
              action: {
                label: 'Undo',
                onPress: async () => {
                  await toggleHide(card.id);
                  toast.success('Restored');
                },
              },
            });
          },
        },
        { label: 'Cancel', kind: 'cancel' },
      ],
    });
  };

  return (
    <Screen edges={['top']}>
      {/* Decorative aurora glow */}
      <LinearGradient
        colors={['#2E1B5B33', '#3B82F622', 'transparent'] as any}
        start={{ x: 0.2, y: 0 }}
        end={{ x: 0.9, y: 0.6 }}
        style={[s.auroraTop, { pointerEvents: 'none' }]}
      />

      <AppHeader
        title={showHiddenOnly ? 'Hidden features' : 'All features'}
        subtitle={
          showHiddenOnly
            ? `Showing ${menuPrefs.hidden.length} hidden card${menuPrefs.hidden.length === 1 ? '' : 's'} · long-press to un-hide`
            : (menuPrefs.pinned.length + menuPrefs.hidden.length > 0)
              ? `${totalCount} features · ${menuPrefs.pinned.length} pinned · ${menuPrefs.hidden.length} hidden`
              : `${totalCount} features · everything in the APK`
        }
        onBack={() => router.back()}
        right={
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <TouchableOpacity
              onPress={() => router.push('/notes')}
              style={s.notesBtn}
              hitSlop={theme.hitSlop.md}
              accessibilityLabel="Open sticky notes"
              testID="header-quick-notes"
            >
              <Ionicons name="document-text" size={16} color="#F5C451" />
            </TouchableOpacity>
            <TouchableOpacity onPress={() => router.push('/hub')} style={s.codeBtn} hitSlop={theme.hitSlop.md}>
              <Ionicons name="code-slash" size={18} color={theme.colors.primary} />
            </TouchableOpacity>
          </View>
        }
      />

      {/* Hidden-only mode banner */}
      {showHiddenOnly && (
        <Pressable
          onPress={() => router.replace('/menu')}
          style={s.hiddenBanner}
          accessibilityLabel="Exit hidden-cards view"
          testID="menu-hidden-banner"
        >
          <Ionicons name="eye-off" size={14} color="#A78BFA" />
          <Text style={s.hiddenBannerText}>
            Showing {menuPrefs.hidden.length} hidden card{menuPrefs.hidden.length === 1 ? '' : 's'}
          </Text>
          <View style={{ flex: 1 }} />
          <Text style={s.hiddenBannerLink}>Show all</Text>
          <Ionicons name="chevron-forward" size={14} color="#A78BFA" />
        </Pressable>
      )}

      {/* Category chips — wrapped with right-edge fade hint so users
          discover the horizontal scroll without guessing */}
      <View style={s.catRowWrap}>
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={s.catRow}
        >
          <Chip label="All" active={!activeCat} onPress={() => setActiveCat(null)} count={totalCount} />
          {CATEGORIES.map(c => (
            <Chip
              key={c.name}
              label={c.name}
              icon={c.icon as any}
              active={activeCat === c.name}
              accentColor={c.color}
              count={c.cards.length}
              onPress={() => setActiveCat(activeCat === c.name ? null : c.name)}
            />
          ))}
        </ScrollView>
        <LinearGradient
          colors={['transparent', theme.colors.bg]}
          start={{ x: 0, y: 0.5 }}
          end={{ x: 1, y: 0.5 }}
          style={[s.catRowFade, { pointerEvents: 'none' }]}
        />
      </View>

      <ScrollView
        ref={scrollRef}
        contentContainerStyle={s.scroll}
        onScroll={onScroll}
        scrollEventThrottle={32}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={theme.colors.primary}
            colors={[theme.colors.primary]}
          />
        }
      >
        {visible.map(cat => (
          <View key={cat.name} style={s.catBlock}>
            <SectionHeader
              label={cat.name}
              count={cat.cards.length}
              accentColor={cat.color}
              right={cat.name === 'Tools' && notesCount > 0 ? (
                <TouchableOpacity
                  onPress={() => router.push('/notes')}
                  hitSlop={theme.hitSlop.md}
                  style={s.notesLiveBadge}
                  accessibilityLabel={`${notesCount} sticky notes`}
                  testID="tools-notes-live"
                >
                  <Ionicons name="document-text" size={10} color="#F5C451" />
                  <Text style={s.notesLiveBadgeText}>{notesCount}</Text>
                </TouchableOpacity>
              ) : undefined}
            />
            <View style={s.grid}>
              {cat.cards.map(card => (
                <FeatureCard
                  key={card.id}
                  title={card.title}
                  desc={card.desc}
                  icon={card.icon as any}
                  color={card.color}
                  hot={card.hot}
                  pinned={menuPrefs.pinned.includes(card.id)}
                  onPress={() => onTap(card)}
                  onLongPress={() => showCardSheet(card)}
                  testID={`feature-${card.id}`}
                />
              ))}
            </View>
          </View>
        ))}
        {visible.length === 0 && (
          <View style={s.emptyBox}>
            <Ionicons name="search-outline" size={44} color={theme.colors.textDim} />
            <Text style={s.emptyText}>No features match “{query}”</Text>
            <Pressable
              onPress={() => { setQuery(''); setActiveCat(null); }}
              style={({ pressed }) => [s.emptyBtn, pressed && { opacity: 0.8 }]}
            >
              <Text style={s.emptyBtnText}>Clear filters</Text>
            </Pressable>
          </View>
        )}
        <View style={{ height: 48 }} />
      </ScrollView>

      {/* Scroll-to-top FAB — appears after the user scrolls past ~600px */}
      <RNAnimated.View
        style={[s.fab, { opacity: fabOpacity, pointerEvents: showFab ? 'auto' : 'none' }]}
      >
        <TouchableOpacity
          onPress={scrollToTop}
          accessibilityLabel="Scroll to top"
          testID="menu-scroll-top"
          style={s.fabInner}
          activeOpacity={0.85}
        >
          <Ionicons name="chevron-up" size={22} color={theme.colors.bg} />
        </TouchableOpacity>
      </RNAnimated.View>

      <View style={s.searchWrap}>
        <SearchBar
          value={query}
          onChangeText={setQuery}
          placeholder="Search features…"
          testID="menu-search"
        />
      </View>
    </Screen>
  );
}

const s = StyleSheet.create({
  auroraTop: {
    position: 'absolute', top: 0, left: 0, right: 0, height: 280,
  },
  codeBtn: {
    width: 38, height: 38, borderRadius: theme.radii.md,
    backgroundColor: theme.colors.primarySoft,
    borderWidth: 1, borderColor: theme.colors.primary + '44',
    justifyContent: 'center', alignItems: 'center',
  },
  notesBtn: {
    width: 38, height: 38, borderRadius: theme.radii.md,
    backgroundColor: '#F5C45122',
    borderWidth: 1, borderColor: '#F5C45166',
    justifyContent: 'center', alignItems: 'center',
  },
  notesLiveBadge: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    paddingHorizontal: 8, paddingVertical: 3,
    backgroundColor: '#F5C45118',
    borderColor: '#F5C45155', borderWidth: 1,
    borderRadius: theme.radii.full,
  },
  notesLiveBadgeText: {
    color: '#F5C451', fontSize: 10, fontWeight: '800', letterSpacing: 0.4,
  },
  hiddenBanner: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    marginHorizontal: 16, marginTop: 8, marginBottom: 2,
    paddingHorizontal: 12, paddingVertical: 10,
    borderRadius: 10, borderWidth: 1,
    backgroundColor: '#A78BFA1A', borderColor: '#A78BFA55',
  },
  hiddenBannerText: { color: '#E2E8F0', fontSize: 12, fontWeight: '600' },
  hiddenBannerLink: { color: '#A78BFA', fontSize: 12, fontWeight: '800' },
  fab: {
    position: 'absolute',
    right: 18,
    bottom: 28,
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: theme.colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
    ...(Platform.OS === 'web' ? {
      // @ts-ignore — web-only style key
      boxShadow: '0 4px 12px rgba(124,58,237,0.45)',
    } : {
      shadowColor: theme.colors.primary,
      shadowOffset: { width: 0, height: 4 },
      shadowOpacity: 0.45,
      shadowRadius: 12,
      elevation: 8,
    }),
  },
  fabInner: {
    width: '100%', height: '100%',
    justifyContent: 'center', alignItems: 'center',
  },
  searchWrap: {
    paddingHorizontal: theme.spacing.base,
    paddingTop: theme.spacing.xs,
    paddingBottom: theme.spacing.sm,
  },
  catRowWrap: {
    position: 'relative',
  },
  catRow: {
    paddingLeft: theme.spacing.base,
    paddingRight: theme.spacing.base + 28,
    paddingBottom: theme.spacing.md,
    gap: theme.spacing.xs,
  },
  catRowFade: {
    position: 'absolute',
    right: 0, top: 0, bottom: 0,
    width: 32,
  },
  scroll: {
    paddingHorizontal: theme.spacing.base,
    paddingBottom: theme.spacing.xl,
  },
  catBlock: {
    marginBottom: theme.spacing.xl,
  },
  catHead: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: theme.spacing.sm,
    marginBottom: theme.spacing.md,
    paddingHorizontal: 2,
  },
  catBadge: {
    width: 22, height: 22, borderRadius: theme.radii.sm,
    borderWidth: 1,
    justifyContent: 'center', alignItems: 'center',
  },
  catTitle: {
    fontSize: 13, fontWeight: '800', letterSpacing: -0.1,
    flex: 1,
  },
  catCountWrap: {
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.full,
    paddingHorizontal: 8, paddingVertical: 2,
    borderWidth: 1, borderColor: theme.colors.border,
  },
  catCount: {
    color: theme.colors.textMuted,
    fontSize: 10, fontWeight: '800',
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.md,
    paddingHorizontal: 2,
    paddingTop: 4,
    paddingBottom: 12,
  },
  emptyBox: {
    padding: theme.spacing['2xl'],
    alignItems: 'center',
    gap: theme.spacing.md,
  },
  emptyText: {
    color: theme.colors.textMuted,
    fontSize: 14,
    fontWeight: '600',
  },
  emptyBtn: {
    backgroundColor: theme.colors.primary,
    borderRadius: theme.radii.md,
    paddingHorizontal: theme.spacing.lg,
    paddingVertical: theme.spacing.sm,
  },
  emptyBtnText: {
    color: '#FFFFFF',
    fontSize: 13, fontWeight: '700',
  },
});
