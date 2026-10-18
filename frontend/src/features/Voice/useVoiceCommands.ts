// ============================================================================
// CODEDOCK QUANTUM NEXUS - Voice Command Interface
// Web Speech API Integration for Hands-Free Control
// ============================================================================

import { useState, useEffect, useCallback, useRef } from 'react';
import { Platform } from 'react-native';

export interface VoiceCommand {
  pattern: RegExp;
  action: string;
  description: string;
  examples: string[];
}

export interface VoiceState {
  isListening: boolean;
  isSupported: boolean;
  transcript: string;
  lastCommand: string | null;
  confidence: number;
  error: string | null;
}

// Command patterns for the compiler
export const VOICE_COMMANDS: VoiceCommand[] = [
  // Optimization commands
  { pattern: /engage (lto|link.?time)/i, action: 'ENABLE_LTO', description: 'Enable Link-Time Optimization', examples: ['Engage LTO', 'Enable link-time optimization'] },
  { pattern: /engage (pgo|profile.?guided)/i, action: 'ENABLE_PGO', description: 'Enable Profile-Guided Optimization', examples: ['Engage PGO', 'Enable profile-guided optimization'] },
  { pattern: /engage vectorization/i, action: 'ENABLE_VECTORIZATION', description: 'Enable auto-vectorization', examples: ['Engage vectorization'] },
  { pattern: /disengage (lto|link.?time)/i, action: 'DISABLE_LTO', description: 'Disable LTO', examples: ['Disengage LTO'] },
  { pattern: /disengage (pgo|profile.?guided)/i, action: 'DISABLE_PGO', description: 'Disable PGO', examples: ['Disengage PGO'] },
  { pattern: /set optimization (level )?(o[0-3s]|ofast|oz)/i, action: 'SET_OPT_LEVEL', description: 'Set optimization level', examples: ['Set optimization O3', 'Set optimization level Ofast'] },
  { pattern: /maximum (performance|power|optimization)/i, action: 'MAX_PERFORMANCE', description: 'Enable all performance optimizations', examples: ['Maximum performance', 'Maximum power'] },
  
  // Sanitizer commands
  { pattern: /raise shields( on line (\d+))?/i, action: 'ENABLE_ALL_SANITIZERS', description: 'Enable all sanitizers', examples: ['Raise shields', 'Raise shields on line 42'] },
  { pattern: /lower shields/i, action: 'DISABLE_ALL_SANITIZERS', description: 'Disable all sanitizers', examples: ['Lower shields'] },
  { pattern: /enable (address|memory|thread|undefined|leak) sanitizer/i, action: 'ENABLE_SANITIZER', description: 'Enable specific sanitizer', examples: ['Enable address sanitizer', 'Enable memory sanitizer'] },
  { pattern: /scan for (memory|thread|undefined|security) (issues|errors|bugs)/i, action: 'RUN_SANITIZER_SCAN', description: 'Run sanitizer scan', examples: ['Scan for memory issues', 'Scan for thread errors'] },
  
  // Analysis commands
  { pattern: /run (full )?analysis/i, action: 'RUN_ANALYSIS', description: 'Run full code analysis', examples: ['Run analysis', 'Run full analysis'] },
  { pattern: /explain (this )?(pass|code|error|warning)/i, action: 'EXPLAIN', description: 'Get AI explanation', examples: ['Explain this pass', 'Explain this error'] },
  { pattern: /what('s| is) (the )?(complexity|performance|issue)/i, action: 'GET_METRICS', description: 'Get code metrics', examples: ["What's the complexity", "What is the performance"] },
  { pattern: /show (ir|intermediate|assembly|ast|cfg)/i, action: 'SHOW_IR', description: 'Show IR/AST/CFG view', examples: ['Show IR', 'Show assembly', 'Show AST'] },
  
  // Compute target commands
  { pattern: /target (cpu|gpu|npu|tpu|fpga|auto)/i, action: 'SET_TARGET', description: 'Set compute target', examples: ['Target GPU', 'Target NPU', 'Target auto'] },
  { pattern: /switch to (cpu|gpu|npu) mode/i, action: 'SET_TARGET', description: 'Switch compute mode', examples: ['Switch to GPU mode'] },
  
  // Energy commands
  { pattern: /set (energy|power) (profile )?(ultra.?low|low|balanced|performance|max)/i, action: 'SET_ENERGY', description: 'Set energy profile', examples: ['Set energy profile balanced', 'Set power max'] },
  { pattern: /conserve (energy|power|battery)/i, action: 'ENERGY_SAVE', description: 'Enable energy saving mode', examples: ['Conserve energy', 'Conserve battery'] },
  
  // Code commands
  { pattern: /run (the )?(code|program)/i, action: 'RUN_CODE', description: 'Execute the code', examples: ['Run the code', 'Run program'] },
  { pattern: /clear (the )?(code|editor)/i, action: 'CLEAR_CODE', description: 'Clear the editor', examples: ['Clear the code', 'Clear editor'] },
  { pattern: /save (the )?(file|code)/i, action: 'SAVE_FILE', description: 'Save current file', examples: ['Save the file', 'Save code'] },
  { pattern: /load template (\w+)/i, action: 'LOAD_TEMPLATE', description: 'Load a template', examples: ['Load template hello world'] },
  
  // Navigation commands
  { pattern: /open (compiler|bible|settings|files|templates)/i, action: 'OPEN_MODAL', description: 'Open a modal', examples: ['Open compiler', 'Open bible', 'Open settings'] },
  { pattern: /close (this|modal|menu)/i, action: 'CLOSE_MODAL', description: 'Close current modal', examples: ['Close this', 'Close modal'] },
  { pattern: /switch (to )?(tab|view) (\w+)/i, action: 'SWITCH_TAB', description: 'Switch compiler tab', examples: ['Switch to tab sanitizers', 'Switch view optimizers'] },
  
  // Language commands
  { pattern: /switch (to |language )?(python|javascript|cpp|c\+\+|rust|go|html)/i, action: 'SWITCH_LANGUAGE', description: 'Switch programming language', examples: ['Switch to Python', 'Switch language Rust'] },
  
  // Version control commands
  { pattern: /create (snapshot|checkpoint|save.?point)/i, action: 'CREATE_SNAPSHOT', description: 'Create version snapshot', examples: ['Create snapshot', 'Create checkpoint'] },
  { pattern: /rollback( to (\w+))?/i, action: 'ROLLBACK', description: 'Rollback to previous version', examples: ['Rollback', 'Rollback to main'] },
  { pattern: /create branch (\w+)/i, action: 'CREATE_BRANCH', description: 'Create new branch', examples: ['Create branch experiment'] },
  
  // Help commands
  { pattern: /help|what can (you|i) (do|say)/i, action: 'HELP', description: 'Show voice commands', examples: ['Help', 'What can you do', 'What can I say'] },
  { pattern: /computer|hey (dock|codedock)/i, action: 'ACTIVATE', description: 'Activate voice assistant', examples: ['Computer', 'Hey CodeDock'] },
];

export function useVoiceCommands(onCommand: (action: string, params?: any) => void) {
  const [state, setState] = useState<VoiceState>({
    isListening: false,
    isSupported: false,
    transcript: '',
    lastCommand: null,
    confidence: 0,
    error: null,
  });
  
  const recognitionRef = useRef<any>(null);
  const isWebRef = useRef(Platform.OS === 'web');

  useEffect(() => {
    if (!isWebRef.current) {
      setState(prev => ({ ...prev, isSupported: false, error: 'Voice commands only available on web' }));
      return;
    }

    // Check for Web Speech API support
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    
    if (!SpeechRecognition) {
      setState(prev => ({ ...prev, isSupported: false, error: 'Speech recognition not supported in this browser' }));
      return;
    }

    setState(prev => ({ ...prev, isSupported: true }));
    
    // Initialize recognition
    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';
    
    recognition.onstart = () => {
      setState(prev => ({ ...prev, isListening: true, error: null }));
    };
    
    recognition.onend = () => {
      setState(prev => ({ ...prev, isListening: false }));
    };
    
    recognition.onerror = (event: any) => {
      setState(prev => ({ ...prev, error: event.error, isListening: false }));
    };
    
    recognition.onresult = (event: any) => {
      const results = event.results;
      const lastResult = results[results.length - 1];
      
      if (lastResult.isFinal) {
        const transcript = lastResult[0].transcript.trim();
        const confidence = lastResult[0].confidence;
        
        setState(prev => ({ ...prev, transcript, confidence }));
        
        // Process command
        processCommand(transcript, confidence);
      } else {
        // Interim result
        const interimTranscript = lastResult[0].transcript;
        setState(prev => ({ ...prev, transcript: interimTranscript }));
      }
    };
    
    recognitionRef.current = recognition;
    
    return () => {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.stop();
        } catch {}
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const processCommand = useCallback((transcript: string, confidence: number) => {
    for (const cmd of VOICE_COMMANDS) {
      const match = transcript.match(cmd.pattern);
      if (match) {
        setState(prev => ({ ...prev, lastCommand: cmd.action }));
        
        // Extract parameters from match groups
        const params: any = { raw: transcript, confidence };
        if (match.length > 1) {
          params.captures = match.slice(1);
        }
        
        // Special parameter extraction
        if (cmd.action === 'SET_OPT_LEVEL') {
          const levelMatch = transcript.match(/o[0-3s]|ofast|oz/i);
          if (levelMatch) params.level = levelMatch[0].toUpperCase();
        }
        if (cmd.action === 'SET_TARGET') {
          const targetMatch = transcript.match(/cpu|gpu|npu|tpu|fpga|auto/i);
          if (targetMatch) params.target = targetMatch[0].toLowerCase();
        }
        if (cmd.action === 'ENABLE_SANITIZER' || cmd.action === 'RUN_SANITIZER_SCAN') {
          const sanitizerMatch = transcript.match(/address|memory|thread|undefined|leak|security/i);
          if (sanitizerMatch) params.sanitizer = sanitizerMatch[0].toLowerCase();
        }
        if (cmd.action === 'SWITCH_LANGUAGE') {
          const langMatch = transcript.match(/python|javascript|cpp|c\+\+|rust|go|html/i);
          if (langMatch) params.language = langMatch[0].toLowerCase().replace('c++', 'cpp');
        }
        if (cmd.action === 'OPEN_MODAL') {
          const modalMatch = transcript.match(/compiler|bible|settings|files|templates/i);
          if (modalMatch) params.modal = modalMatch[0].toLowerCase();
        }
        if (cmd.action === 'SET_ENERGY') {
          const profileMatch = transcript.match(/ultra.?low|low|balanced|performance|max/i);
          if (profileMatch) params.profile = profileMatch[0].toLowerCase().replace(/\s+/g, '_');
        }
        
        onCommand(cmd.action, params);
        
        // Speak confirmation (optional)
        speak(`${cmd.description}`);
        
        return;
      }
    }
    
    // No match found
    speak("I didn't understand that command. Say 'help' for available commands.");
  }, [onCommand]);

  const startListening = useCallback(() => {
    if (!recognitionRef.current || !state.isSupported) return;
    
    try {
      recognitionRef.current.start();
      speak("Voice commands activated. How can I help?");
    } catch {
      // Already started
    }
  }, [state.isSupported]);

  const stopListening = useCallback(() => {
    if (!recognitionRef.current) return;
    
    try {
      recognitionRef.current.stop();
      speak("Voice commands deactivated.");
    } catch {}
  }, []);

  const toggleListening = useCallback(() => {
    if (state.isListening) {
      stopListening();
    } else {
      startListening();
    }
  }, [state.isListening, startListening, stopListening]);

  return {
    ...state,
    startListening,
    stopListening,
    toggleListening,
    commands: VOICE_COMMANDS,
  };
}

// Text-to-speech helper — routes through Jeeves persona when available
export async function speak(text: string, rate: number = 1.0) {
  // Try Jeeves persona first (works on web + native)
  try {
    const { jeevesSpeak, isJeevesEnabled } = await import('../Academy/jeevesTts');
    if (isJeevesEnabled()) {
      jeevesSpeak(text, { context: 'alert', prependCatchphrase: false });
      return;
    }
  } catch {}

  // Web fallback
  if (Platform.OS !== 'web') {
    try {
      const { ttsSpeak } = await import('../Academy/tts');
      ttsSpeak(text);
    } catch {}
    return;
  }
  const synth = (window as any).speechSynthesis;
  if (!synth) return;

  // Cancel any ongoing speech
  synth.cancel();

  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = rate;
  utterance.pitch = 1.0;
  utterance.volume = 0.8;

  // Try to get a nice voice (prefer male British/Daniel for Jeeves vibe)
  const voices = synth.getVoices();
  const preferredVoice = voices.find((v: any) =>
    v.name.includes('Daniel') || v.name.includes('George') || v.name.includes('Arthur') ||
    v.name.includes('Google') || v.name.includes('Samantha')
  );
  if (preferredVoice) utterance.voice = preferredVoice;

  synth.speak(utterance);
}

export default useVoiceCommands;
