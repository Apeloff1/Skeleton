/**
 * Code to App Pipeline Modal v11.0.0
 * Transform code into complete applications, games, and projects
 */

import React, { useState, useCallback, useMemo } from 'react';
import { API_BASE } from '../../utils/apiBase';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView, TextInput,
  Modal, ActivityIndicator, Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { apiFetch } from '../../utils/apiController';
import { toast } from '../../components/Toast';
import Skeleton from '../../components/ui/Skeleton';
import RetryBanner from '../../components/ui/RetryBanner';
import DnaCockpit from '../Settings/DnaCockpit';
import {
  useSettings, BUILDER_CATEGORIES, BUILDER_DNA_BY_CATEGORY,
} from '../../state/settingsStore';
import { builderPresetsForCategory } from '../../state/builderDnaData';
const API_URL = API_BASE;

interface CodeToAppModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
  currentCode?: string;
  currentLanguage?: string;
  onAppGenerated?: (files: any[]) => void;
}

type TabType = 'app' | 'game' | 'convert' | 'enhance';

export const CodeToAppModal: React.FC<CodeToAppModalProps> = ({
  visible, onClose, colors, currentCode, currentLanguage, onAppGenerated
}) => {
  const [activeTab, setActiveTab] = useState<TabType>('app');
  const [isLoading, setIsLoading] = useState(false);
  
  // App generation state
  const [appType, setAppType] = useState('web');
  const [platform] = useState('web');
  const [includeTests, setIncludeTests] = useState(true);
  const [includeDocs, setIncludeDocs] = useState(true);
  const [includeCI, setIncludeCI] = useState(true);
  
  // Game generation state
  const [gameDesc, setGameDesc] = useState('');
  const [gameType, setGameType] = useState('2d');
  const [gameEngine, setGameEngine] = useState('javascript');
  
  // Convert state
  const [targetLang, setTargetLang] = useState('javascript');
  
  // Enhance state
  const [enhancements, setEnhancements] = useState<string[]>(['error_handling', 'typing']);
  
  // Results
  const [result, setResult] = useState<any>(null);
  /** Builder QoL — last error + last-fired generation function so the
   *  RetryBanner can re-run the operation with one tap. */
  const [lastError, setLastError] = useState<string | null>(null);
  const [lastRetryFn, setLastRetryFn] = useState<(() => Promise<void>) | null>(null);

  // 100-slider cockpit per build category — read & write through Zustand.
  const builderDnaByCat = useSettings(s => s.builder.dnaByCategory);
  const setBuilderDna = useSettings(s => s.setBuilderDna);
  const resetBuilderDnaCategory = useSettings(s => s.resetBuilderDnaCategory);
  const resetBuilderDnaGroup = useSettings(s => s.resetBuilderDnaGroup);
  const activeBuilderCatMeta = useMemo(
    () => BUILDER_CATEGORIES.find(c => c.key === appType),
    [appType],
  );

  const appTypes = [
    { key: 'cli', label: '💻 CLI', desc: 'Command-line tool' },
    { key: 'web', label: '🌐 Web', desc: 'Web application' },
    { key: 'api', label: '⚙️ API', desc: 'REST API service' },
    { key: 'mobile', label: '📱 Mobile', desc: 'Mobile app' },
    { key: 'desktop', label: '🖥️ Desktop', desc: 'Desktop app' },
    { key: 'fullstack', label: '📚 Fullstack', desc: 'Complete stack' },
  ];

  const gameTypes = [
    { key: '2d', label: '🎮 2D' },
    { key: 'puzzle', label: '🧩 Puzzle' },
    { key: 'platformer', label: '🎰 Platformer' },
    { key: 'rpg', label: '⚔️ RPG' },
  ];

  const gameEngines = [
    { key: 'javascript', label: 'JavaScript/HTML5' },
    { key: 'pygame', label: 'Python (Pygame)' },
    { key: 'phaser', label: 'Phaser.js' },
  ];

  const languages = ['python', 'javascript', 'typescript', 'java', 'cpp', 'rust', 'go', 'swift'];
  
  const enhancementOptions = [
    { key: 'error_handling', label: '🛡️ Error Handling' },
    { key: 'typing', label: '🎯 Type Hints' },
    { key: 'logging', label: '📝 Logging' },
    { key: 'validation', label: '✅ Validation' },
    { key: 'security', label: '🔒 Security' },
    { key: 'performance', label: '⚡ Performance' },
    { key: 'documentation', label: '📖 Docs' },
    { key: 'async', label: '↻ Async' },
  ];

  const generateApp = useCallback(async () => {
    if (!currentCode?.trim()) {
      toast.warn('Write some code first');
      return;
    }
    
    setIsLoading(true);
    setResult(null);
    
    try {
      const cockpit = builderDnaByCat[appType] || {};
      const response = await apiFetch(`${API_URL}/api/code-to-app/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: currentCode,
          language: currentLanguage || 'python',
          app_type: appType,
          target_platform: platform,
          include_tests: includeTests,
          include_docs: includeDocs,
          include_cicd: includeCI,
          builder_dna: cockpit,
        }),
      });
      
      const data = await response.json();
      setResult(data);
      
      if (data.status === 'success' && onAppGenerated) {
        onAppGenerated(data.files);
      }
      setLastError(null);
      setLastRetryFn(null);
    } catch (error: any) {
      const msg = `Generation failed: ${error.message}`;
      toast.error(msg);
      setLastError(msg);
      setLastRetryFn(() => generateApp);
    } finally {
      setIsLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentCode, currentLanguage, appType, platform, includeTests, includeDocs, includeCI]);

  const generateGame = useCallback(async () => {
    if (!gameDesc.trim()) {
      toast.warn('Describe your game concept');
      return;
    }
    
    setIsLoading(true);
    setResult(null);
    
    try {
      const response = await apiFetch(`${API_URL}/api/code-to-app/generate-game`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          description: gameDesc,
          game_type: gameType,
          engine: gameEngine,
          include_assets: true,
        }),
      });
      
      const data = await response.json();
      setResult(data);
    } catch (error: any) {
      const msg = `Game generation failed: ${error.message}`;
      toast.error(msg); setLastError(msg); setLastRetryFn(() => generateGame);
    } finally {
      setIsLoading(false);
    }
  }, [gameDesc, gameType, gameEngine]);

  const convertCode = useCallback(async () => {
    if (!currentCode?.trim()) {
      toast.warn('No code to convert');
      return;
    }
    
    setIsLoading(true);
    setResult(null);
    
    try {
      const response = await apiFetch(`${API_URL}/api/code-to-app/convert`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: currentCode,
          from_language: currentLanguage || 'python',
          to_language: targetLang,
        }),
      });
      
      const data = await response.json();
      setResult(data);
    } catch (error: any) {
      const msg = `Conversion failed: ${error.message}`;
      toast.error(msg); setLastError(msg); setLastRetryFn(() => convertCode);
    } finally {
      setIsLoading(false);
    }
  }, [currentCode, currentLanguage, targetLang]);

  const enhanceCode = useCallback(async () => {
    if (!currentCode?.trim()) {
      toast.warn('No code to enhance');
      return;
    }
    
    setIsLoading(true);
    setResult(null);
    
    try {
      const response = await apiFetch(`${API_URL}/api/code-to-app/enhance`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: currentCode,
          language: currentLanguage || 'python',
          enhancements,
        }),
      });
      
      const data = await response.json();
      setResult(data);
    } catch (error: any) {
      const msg = `Enhancement failed: ${error.message}`;
      toast.error(msg); setLastError(msg); setLastRetryFn(() => enhanceCode);
    } finally {
      setIsLoading(false);
    }
  }, [currentCode, currentLanguage, enhancements]);

  const toggleEnhancement = (key: string) => {
    setEnhancements(prev => 
      prev.includes(key) ? prev.filter(e => e !== key) : [...prev, key]
    );
  };

  const renderTabs = () => (
    <View style={[styles.tabs, { borderBottomColor: colors.border }]}>
      {[
        { key: 'app', label: '📦 App' },
        { key: 'game', label: '🎮 Game' },
        { key: 'convert', label: '🔄 Convert' },
        { key: 'enhance', label: '✨ Enhance' },
      ].map((tab) => (
        <TouchableOpacity
          key={tab.key}
          style={[
            styles.tab,
            activeTab === tab.key && { borderBottomColor: colors.primary, borderBottomWidth: 2 }
          ]}
          onPress={() => setActiveTab(tab.key as TabType)}
        >
          <Text style={[styles.tabText, { color: activeTab === tab.key ? colors.primary : colors.textSecondary }]}>
            {tab.label}
          </Text>
        </TouchableOpacity>
      ))}
    </View>
  );

  const renderAppTab = () => (
    <ScrollView style={styles.tabContent} showsVerticalScrollIndicator={false}>
      <Text style={[styles.label, { color: colors.text }]}>📦 Application Type</Text>
      <View style={styles.chipGrid}>
        {appTypes.map((type) => (
          <TouchableOpacity
            key={type.key}
            style={[
              styles.typeChip,
              { backgroundColor: appType === type.key ? colors.primary : colors.cardBackground, borderColor: colors.border }
            ]}
            onPress={() => setAppType(type.key)}
          >
            <Text style={[styles.typeLabel, { color: appType === type.key ? '#FFF' : colors.text }]}>{type.label}</Text>
            <Text style={[styles.typeDesc, { color: appType === type.key ? 'rgba(255,255,255,0.8)' : colors.textSecondary }]}>{type.desc}</Text>
          </TouchableOpacity>
        ))}
      </View>
      
      <Text style={[styles.label, { color: colors.text, marginTop: 16 }]}>⚙️ Options</Text>
      <View style={styles.optionRow}>
        <TouchableOpacity style={styles.checkbox} onPress={() => setIncludeTests(!includeTests)}>
          <Ionicons name={includeTests ? 'checkbox' : 'square-outline'} size={20} color={colors.primary} />
          <Text style={[styles.checkboxLabel, { color: colors.text }]}>Include Tests</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.checkbox} onPress={() => setIncludeDocs(!includeDocs)}>
          <Ionicons name={includeDocs ? 'checkbox' : 'square-outline'} size={20} color={colors.primary} />
          <Text style={[styles.checkboxLabel, { color: colors.text }]}>Include Docs</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.checkbox} onPress={() => setIncludeCI(!includeCI)}>
          <Ionicons name={includeCI ? 'checkbox' : 'square-outline'} size={20} color={colors.primary} />
          <Text style={[styles.checkboxLabel, { color: colors.text }]}>CI/CD Pipeline</Text>
        </TouchableOpacity>
      </View>

      {/* 100-slider production-readiness cockpit for the selected build category.
          Switches automatically when the user picks CLI / Web / API / Mobile / Desktop / Fullstack. */}
      {activeBuilderCatMeta && (
        <View style={{ marginHorizontal: -16, marginTop: 12 }}>
          <DnaCockpit
            title={`${activeBuilderCatMeta.emoji} ${activeBuilderCatMeta.label} Build DNA`}
            groups={BUILDER_DNA_BY_CATEGORY[appType] || []}
            dna={builderDnaByCat[appType] || {}}
            onChange={(key, v) => setBuilderDna(appType, key, v)}
            onResetGroup={(gid) => resetBuilderDnaGroup(appType, gid)}
            onResetAll={() => resetBuilderDnaCategory(appType)}
            accent={activeBuilderCatMeta.color}
            previewEndpoint="/api/code-to-app/dna/preview"
            presets={builderPresetsForCategory(appType)}
          />
        </View>
      )}
      
      <TouchableOpacity
        style={[styles.actionBtn, { backgroundColor: colors.primary }]}
        onPress={generateApp}
        disabled={isLoading || !currentCode}
      >
        {isLoading ? (
          <ActivityIndicator color="#FFF" />
        ) : (
          <>
            <Ionicons name="rocket" size={18} color="#FFF" />
            <Text style={styles.actionBtnText}>Generate Application</Text>
          </>
        )}
      </TouchableOpacity>
      
      {!currentCode && (
        <Text style={[styles.hint, { color: colors.textSecondary }]}>
          💡 Write some code in the editor first, then transform it into a complete app!
        </Text>
      )}
    </ScrollView>
  );

  const renderGameTab = () => (
    <ScrollView style={styles.tabContent} showsVerticalScrollIndicator={false}>
      <Text style={[styles.label, { color: colors.text }]}>🎮 Describe Your Game</Text>
      <TextInput
        style={[styles.textArea, { backgroundColor: colors.codeBackground, color: colors.text, borderColor: colors.border }]}
        placeholder="A puzzle game where players match colored blocks..."
        placeholderTextColor={colors.textSecondary}
        value={gameDesc}
        onChangeText={setGameDesc}
        multiline
        numberOfLines={4}
      />
      
      <Text style={[styles.label, { color: colors.text, marginTop: 16 }]}>🎯 Game Type</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false}>
        {gameTypes.map((type) => (
          <TouchableOpacity
            key={type.key}
            style={[
              styles.langChip,
              { backgroundColor: gameType === type.key ? colors.primary : colors.cardBackground, borderColor: colors.border }
            ]}
            onPress={() => setGameType(type.key)}
          >
            <Text style={[styles.langChipText, { color: gameType === type.key ? '#FFF' : colors.text }]}>{type.label}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>
      
      <Text style={[styles.label, { color: colors.text, marginTop: 16 }]}>🛠️ Engine</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false}>
        {gameEngines.map((engine) => (
          <TouchableOpacity
            key={engine.key}
            style={[
              styles.langChip,
              { backgroundColor: gameEngine === engine.key ? colors.primary : colors.cardBackground, borderColor: colors.border }
            ]}
            onPress={() => setGameEngine(engine.key)}
          >
            <Text style={[styles.langChipText, { color: gameEngine === engine.key ? '#FFF' : colors.text }]}>{engine.label}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>
      
      <TouchableOpacity
        style={[styles.actionBtn, { backgroundColor: colors.primary, marginTop: 20 }]}
        onPress={generateGame}
        disabled={isLoading}
      >
        {isLoading ? (
          <ActivityIndicator color="#FFF" />
        ) : (
          <>
            <Ionicons name="game-controller" size={18} color="#FFF" />
            <Text style={styles.actionBtnText}>Generate Game</Text>
          </>
        )}
      </TouchableOpacity>
    </ScrollView>
  );

  const renderConvertTab = () => (
    <ScrollView style={styles.tabContent} showsVerticalScrollIndicator={false}>
      <Text style={[styles.label, { color: colors.text }]}>🔄 Convert {currentLanguage || 'code'} to:</Text>
      <View style={styles.chipGrid}>
        {languages.filter(l => l !== currentLanguage).map((lang) => (
          <TouchableOpacity
            key={lang}
            style={[
              styles.langChip,
              { backgroundColor: targetLang === lang ? colors.primary : colors.cardBackground, borderColor: colors.border }
            ]}
            onPress={() => setTargetLang(lang)}
          >
            <Text style={[styles.langChipText, { color: targetLang === lang ? '#FFF' : colors.text }]}>
              {lang.charAt(0).toUpperCase() + lang.slice(1)}
            </Text>
          </TouchableOpacity>
        ))}
      </View>
      
      <TouchableOpacity
        style={[styles.actionBtn, { backgroundColor: colors.primary, marginTop: 20 }]}
        onPress={convertCode}
        disabled={isLoading || !currentCode}
      >
        {isLoading ? (
          <ActivityIndicator color="#FFF" />
        ) : (
          <>
            <Ionicons name="swap-horizontal" size={18} color="#FFF" />
            <Text style={styles.actionBtnText}>Convert Code</Text>
          </>
        )}
      </TouchableOpacity>
    </ScrollView>
  );

  const renderEnhanceTab = () => (
    <ScrollView style={styles.tabContent} showsVerticalScrollIndicator={false}>
      <Text style={[styles.label, { color: colors.text }]}>✨ Select Enhancements</Text>
      <View style={styles.chipGrid}>
        {enhancementOptions.map((opt) => (
          <TouchableOpacity
            key={opt.key}
            style={[
              styles.enhanceChip,
              { backgroundColor: enhancements.includes(opt.key) ? colors.primary : colors.cardBackground, borderColor: colors.border }
            ]}
            onPress={() => toggleEnhancement(opt.key)}
          >
            <Text style={[styles.enhanceText, { color: enhancements.includes(opt.key) ? '#FFF' : colors.text }]}>{opt.label}</Text>
          </TouchableOpacity>
        ))}
      </View>
      
      <TouchableOpacity
        style={[styles.actionBtn, { backgroundColor: colors.primary, marginTop: 20 }]}
        onPress={enhanceCode}
        disabled={isLoading || !currentCode || enhancements.length === 0}
      >
        {isLoading ? (
          <ActivityIndicator color="#FFF" />
        ) : (
          <>
            <Ionicons name="sparkles" size={18} color="#FFF" />
            <Text style={styles.actionBtnText}>Enhance Code</Text>
          </>
        )}
      </TouchableOpacity>
    </ScrollView>
  );

  const renderResult = () => {
    // Builder QoL — when a generation/conversion is running, surface a
    // skeleton paragraph so users see "something is happening" instantly.
    if (isLoading) {
      return (
        <View style={[styles.resultCard, { backgroundColor: colors.cardBackground, borderColor: colors.border }]}>
          <Text style={[styles.resultTitle, { color: colors.text }]}>Working…</Text>
          <Skeleton.Block rows={4} gap={10} lastWidth="55%" />
        </View>
      );
    }
    // After a failure surfaces a RetryBanner with one-tap "Retry last action".
    if (lastError && lastRetryFn) {
      return (
        <View style={{ paddingHorizontal: 16, paddingTop: 8 }}>
          <RetryBanner
            error={lastError}
            onRetry={() => { setLastError(null); lastRetryFn(); }}
            retryLabel="Retry last action"
          />
        </View>
      );
    }
    if (!result) return null;
    
    return (
      <View style={[styles.resultCard, { backgroundColor: colors.cardBackground, borderColor: colors.border }]}>
        <Text style={[styles.resultTitle, { color: colors.text }]}>
          {result.status === 'success' ? '✅ Generated Successfully' : '❌ Generation Failed'}
        </Text>
        
        {result.files?.length > 0 && (
          <>
            <Text style={[styles.resultSubtitle, { color: colors.textSecondary }]}>
              {result.files.length} files generated
            </Text>
            <ScrollView style={styles.fileList} nestedScrollEnabled>
              {result.files.slice(0, 10).map((file: any, i: number) => (
                <View key={i} style={[styles.fileItem, { backgroundColor: colors.codeBackground }]}>
                  <Ionicons name="document-text" size={14} color={colors.primary} />
                  <Text style={[styles.fileName, { color: colors.text }]}>{file.path}</Text>
                </View>
              ))}
            </ScrollView>
          </>
        )}
        
        {result.converted?.code && (
          <View style={[styles.codePreview, { backgroundColor: colors.codeBackground }]}>
            <Text style={[styles.codeText, { color: colors.text }]}>
              {result.converted.code.substring(0, 500)}...
            </Text>
          </View>
        )}
        
        {result.enhanced_code && (
          <View style={[styles.codePreview, { backgroundColor: colors.codeBackground }]}>
            <Text style={[styles.codeText, { color: colors.text }]}>
              {result.enhanced_code.substring(0, 500)}...
            </Text>
          </View>
        )}
      </View>
    );
  };

  return (
    <Modal visible={visible} animationType="slide" transparent={false}>
      <View style={[styles.container, { backgroundColor: colors.background }]}>
        <View style={[styles.header, { borderBottomColor: colors.border }]}>
          <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
            <Ionicons name="close" size={24} color={colors.text} />
          </TouchableOpacity>
          <Text style={[styles.title, { color: colors.text }]}>🚀 Code-to-App Pipeline</Text>
          <View style={styles.placeholder} />
        </View>

        {renderTabs()}
        
        {activeTab === 'app' && renderAppTab()}
        {activeTab === 'game' && renderGameTab()}
        {activeTab === 'convert' && renderConvertTab()}
        {activeTab === 'enhance' && renderEnhanceTab()}
        
        {renderResult()}
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, paddingTop: Platform.OS === 'ios' ? 50 : 30 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingBottom: 12, borderBottomWidth: 1 },
  closeBtn: { padding: 8 },
  title: { fontSize: 18, fontWeight: 'bold' },
  placeholder: { width: 40 },
  tabs: { flexDirection: 'row', borderBottomWidth: 1 },
  tab: { flex: 1, paddingVertical: 12, alignItems: 'center' },
  tabText: { fontSize: 13, fontWeight: '600' },
  tabContent: { flex: 1, padding: 16 },
  label: { fontSize: 14, fontWeight: '600', marginBottom: 8 },
  chipGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  typeChip: { width: '48%', padding: 12, borderRadius: 10, borderWidth: 1 },
  typeLabel: { fontSize: 14, fontWeight: '600' },
  typeDesc: { fontSize: 11, marginTop: 2 },
  langChip: { paddingHorizontal: 16, paddingVertical: 10, borderRadius: 20, marginRight: 8, borderWidth: 1 },
  langChipText: { fontSize: 13, fontWeight: '500' },
  enhanceChip: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, borderWidth: 1 },
  enhanceText: { fontSize: 12, fontWeight: '500' },
  optionRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 16, marginBottom: 16 },
  checkbox: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  checkboxLabel: { fontSize: 13 },
  actionBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', padding: 14, borderRadius: 8, gap: 8, marginTop: 16 },
  actionBtnText: { color: '#FFF', fontSize: 14, fontWeight: '600' },
  hint: { fontSize: 12, textAlign: 'center', marginTop: 12 },
  textArea: { borderWidth: 1, borderRadius: 8, padding: 12, fontSize: 14, minHeight: 100, textAlignVertical: 'top' },
  resultCard: { margin: 16, padding: 16, borderRadius: 12, borderWidth: 1 },
  resultTitle: { fontSize: 16, fontWeight: 'bold', marginBottom: 8 },
  resultSubtitle: { fontSize: 12, marginBottom: 12 },
  fileList: { maxHeight: 150 },
  fileItem: { flexDirection: 'row', alignItems: 'center', padding: 8, borderRadius: 6, marginBottom: 4, gap: 8 },
  fileName: { fontSize: 12, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace' },
  codePreview: { padding: 12, borderRadius: 8, marginTop: 12 },
  codeText: { fontSize: 11, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace', lineHeight: 16 },
});

export default CodeToAppModal;
