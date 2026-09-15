/**
 * app/index.styles
 * -------------------------------------------------------------------
 * Extracted from app/index.tsx on 2026-05-15 to drop the host file
 * from 2519 → ~1795 lines and reduce AST/parser timeout risk.
 * No behavior change — these are the exact StyleSheet definitions
 * previously inlined at the bottom of the main hub component.
 */
import { Platform, StyleSheet } from 'react-native';

export const styles = StyleSheet.create({
  // Loading
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingLogo: {
    width: 80,
    height: 80,
    borderRadius: 20,
    backgroundColor: 'rgba(99, 102, 241, 0.1)',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
    alignSelf: 'center',
  },
  loadingTitle: {
    fontSize: 28,
    fontWeight: '800',
    textAlign: 'center',
  },
  loadingSubtitle: {
    fontSize: 14,
    marginTop: 4,
    textAlign: 'center',
  },
  skelGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'center',
    gap: 12,
    marginTop: 28,
    paddingHorizontal: 24,
    maxWidth: 360,
  },
  skelTile: {
    width: 100,
    height: 92,
    borderRadius: 16,
    borderWidth: 1,
    padding: 12,
    justifyContent: 'space-between',
  },
  skelDot: { width: 28, height: 28, borderRadius: 8, opacity: 0.7 },
  skelLine: { width: '80%', height: 9, borderRadius: 4, opacity: 0.6 },
  skelLineSm: { width: '50%', height: 7, borderRadius: 4, opacity: 0.4 },

  // Main Container
  container: {
    flex: 1,
  },

  // Header
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderBottomWidth: 1,
    gap: 6,
  },
  settingsTopLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 0,
    paddingHorizontal: 8,
    paddingVertical: 8,
    borderRadius: 10,
    borderWidth: 1,
    minHeight: 38,
    minWidth: 38,
    justifyContent: 'center',
  },
  settingsTopLeftText: {
    fontSize: 0,            // hide the "Settings" text label to save horizontal real-estate
    width: 0,
    fontWeight: '700',
    letterSpacing: 0.2,
  },
  languageSelector: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingVertical: 4,
    flex: 1,
    flexBasis: 0,
    minWidth: 110,
  },
  langIconBg: {
    width: 36,
    height: 36,
    borderRadius: 10,
    justifyContent: 'center',
    alignItems: 'center',
  },
  langInfo: {
    flexShrink: 1,
    minWidth: 0,
    flex: 1,
  },
  languageName: {
    fontSize: 14,
    fontWeight: '700',
  },
  languageVersion: {
    fontSize: 10,
    marginTop: 1,
  },
  headerActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    flexShrink: 0,
  },
  headerButton: {
    padding: 8,
    borderRadius: 10,
    minWidth: 38,
    minHeight: 38,
    justifyContent: 'center',
    alignItems: 'center',
  },
  headerXpBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    paddingHorizontal: 6,
    paddingVertical: 4,
    borderRadius: 8,
  },
  headerXpText: {
    color: '#F59E0B',
    fontSize: 11,
    fontWeight: '700',
  },
  headerPipelineBadge: {
    padding: 6,
    borderRadius: 8,
  },

  // Error Banner
  errorBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderBottomWidth: 1,
  },
  errorContent: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    flex: 1,
  },
  errorText: {
    fontSize: 13,
    fontWeight: '500',
    flex: 1,
  },
  retryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
    gap: 4,
  },
  retryText: {
    color: '#FFF',
    fontSize: 12,
    fontWeight: '600',
  },

  // Toolbar
  toolbar: {
    paddingVertical: 8,
    paddingHorizontal: 8,
  },
  toolbarContent: {
    paddingHorizontal: 8,
    gap: 8,
  },
  toolButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 8,
    gap: 6,
  },
  toolButtonText: {
    fontSize: 13,
    fontWeight: '600',
  },

  // AI Bar
  aiBar: {
    paddingVertical: 10,
  },
  aiBarContent: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    gap: 10,
  },
  aiBarClean: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    gap: 10,
  },
  aiButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 10,
    borderWidth: 1,
    gap: 8,
  },
  aiButtonText: {
    fontSize: 14,
    fontWeight: '700',
  },
  aiBadge: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
  },
  aiBadgeText: {
    color: '#FFF',
    fontSize: 10,
    fontWeight: '700',
  },
  commandPaletteButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 10,
    borderWidth: 1,
    gap: 8,
    flex: 1,
  },
  commandPaletteText: {
    fontSize: 14,
    fontWeight: '600',
  },
  featureCountBadge: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
    marginLeft: 'auto',
  },
  featureCountText: {
    color: '#FFF',
    fontSize: 10,
    fontWeight: '700',
  },
  quickAccessChip: {
    width: 40,
    height: 40,
    borderRadius: 10,
    justifyContent: 'center',
    alignItems: 'center',
  },
  featureChip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 8,
    gap: 6,
  },
  featureChipText: {
    fontSize: 13,
    fontWeight: '600',
  },

  // Editor
  mainContent: {
    flex: 1,
  },
  editorContainer: {
    flex: 1,
  },
  editorHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderBottomWidth: 1,
  },
  editorTab: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
    borderBottomWidth: 2,
  },
  fileNameInput: {
    fontSize: 14,
    fontWeight: '600',
    minWidth: 80,
  },
  extensionText: {
    fontSize: 12,
  },
  execTime: {
    fontSize: 12,
    fontWeight: '600',
  },
  editorScroll: {
    flex: 1,
  },
  editorContent: {
    flexDirection: 'row',
    minHeight: 300,
  },
  lineNumbers: {
    paddingVertical: 12,
    paddingHorizontal: 12,
    alignItems: 'flex-end',
  },
  lineNumber: {
    fontSize: 13,
    lineHeight: 22,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  codeInput: {
    flex: 1,
    fontSize: 14,
    lineHeight: 22,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    paddingVertical: 12,
    paddingHorizontal: 12,
    textAlignVertical: 'top',
  },

  // Output
  outputContainer: {
    height: 180,
    borderTopWidth: 1,
  },
  outputHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderBottomWidth: 1,
  },
  outputTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  outputTitle: {
    fontSize: 14,
    fontWeight: '700',
  },
  outputScroll: {
    flex: 1,
    padding: 12,
  },
  outputText: {
    fontSize: 13,
    lineHeight: 20,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  webPreview: {
    flex: 1,
  },

  // Bottom Bar
  bottomBar: {
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderTopWidth: 1,
  },
  runButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 14,
    borderRadius: 12,
    gap: 10,
  },
  runButtonText: {
    color: '#FFF',
    fontSize: 16,
    fontWeight: '700',
  },

  // Modal Base
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    maxHeight: '80%',
    minHeight: 300,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
  },
  modalHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: 1,
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: '700',
  },
  modalScroll: {
    padding: 16,
  },
  emptyState: {
    alignItems: 'center',
    paddingVertical: 40,
  },
  emptyText: {
    fontSize: 15,
    marginTop: 12,
    textAlign: 'center',
  },
  emptyHint: {
    fontSize: 13,
    marginTop: 4,
    textAlign: 'center',
  },

  // Language Modal Items
  langItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 14,
    borderRadius: 12,
    marginBottom: 10,
    borderWidth: 1.5,
  },
  langItemIcon: {
    width: 44,
    height: 44,
    borderRadius: 12,
    justifyContent: 'center',
    alignItems: 'center',
  },
  langItemInfo: {
    flex: 1,
    marginLeft: 12,
  },
  langItemName: {
    fontSize: 16,
    fontWeight: '700',
  },
  langItemDesc: {
    fontSize: 12,
    marginTop: 2,
  },
  execBadge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 6,
  },
  execBadgeText: {
    fontSize: 11,
    fontWeight: '700',
  },

  // Template Items
  templateItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 14,
    borderRadius: 12,
    marginBottom: 10,
    gap: 12,
  },
  templateInfo: {
    flex: 1,
  },
  templateName: {
    fontSize: 15,
    fontWeight: '600',
  },
  templateDesc: {
    fontSize: 12,
    marginTop: 2,
  },

  // File Items
  fileItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 14,
    borderRadius: 12,
    marginBottom: 10,
    gap: 12,
  },
  fileInfo: {
    flex: 1,
  },
  fileName: {
    fontSize: 15,
    fontWeight: '600',
  },
  fileMeta: {
    fontSize: 12,
    marginTop: 2,
  },

  // AI Modal
  aiModalTitle: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  aiSectionTitle: {
    fontSize: 13,
    fontWeight: '600',
    marginBottom: 12,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  aiModeItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 14,
    paddingRight: 12,
    borderRadius: 12,
    marginBottom: 10,
    gap: 12,
    minHeight: 72,
  },
  aiModeIcon: {
    width: 44,
    height: 44,
    borderRadius: 12,
    justifyContent: 'center',
    alignItems: 'center',
    flexShrink: 0,
  },
  aiModeInfo: {
    flex: 1,
    minWidth: 0,
    paddingRight: 4,
  },
  aiModeName: {
    fontSize: 15,
    fontWeight: '700',
    flexShrink: 1,
  },
  aiModeDesc: {
    fontSize: 12,
    marginTop: 3,
    lineHeight: 16,
    flexShrink: 1,
  },
  aiResponseContainer: {
    flex: 1,
  },
  aiResponseHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    gap: 12,
  },
  aiBackButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  aiBackText: {
    fontSize: 14,
    fontWeight: '600',
  },
  aiModeLabel: {
    fontSize: 15,
    fontWeight: '600',
  },
  aiLoading: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 60,
  },
  aiLoadingText: {
    marginTop: 16,
    fontSize: 14,
  },
  aiResponseScroll: {
    flex: 1,
    padding: 16,
  },
  aiResponseText: {
    fontSize: 14,
    lineHeight: 22,
  },

  // Settings Modal
  settingItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 14,
    borderRadius: 12,
    marginBottom: 10,
    gap: 12,
  },
  settingInfo: {
    flex: 1,
  },
  settingName: {
    fontSize: 15,
    fontWeight: '600',
  },
  settingValue: {
    fontSize: 12,
    marginTop: 2,
  },
  aboutSection: {
    padding: 20,
    borderRadius: 12,
    alignItems: 'center',
    marginTop: 20,
  },
  aboutTitle: {
    fontSize: 20,
    fontWeight: '800',
  },
  aboutVersion: {
    fontSize: 13,
    marginTop: 4,
  },
  aboutDesc: {
    fontSize: 12,
    marginTop: 8,
    textAlign: 'center',
  },

  // Tutorial Modal
  tutorialOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.7)',
    justifyContent: 'center',
    padding: 20,
  },
  tutorialCard: {
    borderRadius: 20,
    maxHeight: '80%',
    overflow: 'hidden',
  },
  tutorialHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: 1,
  },
  tutorialProgress: {
    flex: 1,
    marginRight: 16,
  },
  tutorialStep: {
    fontSize: 12,
    fontWeight: '600',
    marginBottom: 6,
  },
  progressBar: {
    height: 4,
    borderRadius: 2,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    borderRadius: 2,
  },
  skipText: {
    fontSize: 14,
    fontWeight: '600',
  },
  tutorialContent: {
    padding: 20,
  },
  tutorialIcon: {
    width: 80,
    height: 80,
    borderRadius: 20,
    justifyContent: 'center',
    alignItems: 'center',
    alignSelf: 'center',
    marginBottom: 16,
  },
  tutorialTitle: {
    fontSize: 24,
    fontWeight: '800',
    textAlign: 'center',
    marginBottom: 8,
  },
  tutorialDesc: {
    fontSize: 15,
    textAlign: 'center',
    marginBottom: 16,
  },
  tutorialContentText: {
    fontSize: 14,
    lineHeight: 22,
  },
  tutorialTips: {
    padding: 14,
    borderRadius: 12,
    marginTop: 16,
  },
  tipsTitle: {
    fontSize: 14,
    fontWeight: '700',
    marginBottom: 8,
  },
  tipText: {
    fontSize: 13,
    lineHeight: 22,
  },
  tutorialNav: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 16,
    borderTopWidth: 1,
  },
  tutorialNavBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 12,
    borderRadius: 10,
    gap: 6,
  },
  tutorialNavPrimary: {
    paddingHorizontal: 24,
  },
  tutorialNavText: {
    fontSize: 14,
    fontWeight: '600',
  },
  tutorialNavTextPrimary: {
    color: '#FFF',
    fontSize: 14,
    fontWeight: '700',
  },
});
