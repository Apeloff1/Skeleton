// ============================================================================
// CODEDOCK QUANTUM COMPILER SUITE - Type Definitions
// Version: 6.0.0 | 2026+ Bleeding-Edge Standards
// ============================================================================

// ============================================================================
// SANITIZER TYPES
// ============================================================================
export type SanitizerType = 
  | 'address'      // AddressSanitizer - Memory errors
  | 'thread'       // ThreadSanitizer - Data races
  | 'undefined'    // UBSan - Undefined behavior
  | 'memory'       // MemorySanitizer - Uninitialized reads
  | 'leak'         // LeakSanitizer - Memory leaks
  | 'bounds'       // Bounds checking
  | 'null'         // Null pointer detection
  | 'type'         // Type confusion
  | 'lifetime';    // Lifetime analysis

export interface SanitizerResult {
  type: SanitizerType;
  severity: 'info' | 'warning' | 'error' | 'critical';
  line: number;
  column: number;
  message: string;
  code: string;
  suggestion?: string;
  fixIt?: {
    description: string;
    replacement: string;
    range: { start: number; end: number };
  };
}

// ============================================================================
// OPTIMIZATION TYPES
// ============================================================================
export type OptimizationLevel = 'O0' | 'O1' | 'O2' | 'O3' | 'Os' | 'Oz' | 'Ofast';

export type OptimizationType =
  | 'lto'              // Link-Time Optimization
  | 'pgo'              // Profile-Guided Optimization
  | 'vectorization'    // Auto-vectorization (SIMD)
  | 'loop_unroll'      // Loop unrolling
  | 'inlining'         // Function inlining
  | 'dead_code'        // Dead code elimination
  | 'const_prop'       // Constant propagation
  | 'const_fold'       // Constant folding
  | 'tail_call'        // Tail call optimization
  | 'devirt'           // Devirtualization
  | 'mem2reg'          // Memory to register promotion
  | 'instcombine'      // Instruction combining
  | 'reassociate'      // Reassociation
  | 'gvn'              // Global value numbering
  | 'licm'             // Loop invariant code motion
  | 'sroa'             // Scalar replacement of aggregates
  | 'ml_guided';       // ML-guided optimization

export interface OptimizationPass {
  type: OptimizationType;
  enabled: boolean;
  description: string;
  impact: 'low' | 'medium' | 'high' | 'critical';
  tradeoffs?: string[];
}

export interface OptimizationResult {
  pass: OptimizationType;
  applied: boolean;
  improvements: {
    metric: string;
    before: number;
    after: number;
    percentChange: number;
  }[];
  codeChanges?: string[];
}

// ============================================================================
// DIAGNOSTIC TYPES
// ============================================================================
export type DiagnosticSeverity = 'hint' | 'info' | 'warning' | 'error' | 'fatal';

export interface Diagnostic {
  id: string;
  severity: DiagnosticSeverity;
  source: 'compiler' | 'linter' | 'sanitizer' | 'ai' | 'lsp';
  message: string;
  line: number;
  column: number;
  endLine?: number;
  endColumn?: number;
  code?: string;
  category: string;
  explanation?: string;
  suggestions?: string[];
  fixIts?: FixIt[];
  relatedInfo?: RelatedDiagnostic[];
}

export interface FixIt {
  description: string;
  isPreferred: boolean;
  changes: {
    range: { startLine: number; startCol: number; endLine: number; endCol: number };
    newText: string;
  }[];
}

export interface RelatedDiagnostic {
  message: string;
  location: { line: number; column: number };
}

// ============================================================================
// HETEROGENEOUS COMPUTING
// ============================================================================
export type ComputeTarget = 'cpu' | 'gpu' | 'npu' | 'tpu' | 'fpga' | 'auto';

export interface ComputeCapability {
  target: ComputeTarget;
  available: boolean;
  cores?: number;
  memory?: number;
  computeUnits?: number;
  features: string[];
}

export interface HeterogeneousConfig {
  primaryTarget: ComputeTarget;
  fallbackTargets: ComputeTarget[];
  autoDispatch: boolean;
  energyAware: boolean;
  preferenceMode: 'performance' | 'efficiency' | 'balanced';
}

// ============================================================================
// ENERGY OPTIMIZATION
// ============================================================================
export type EnergyProfile = 'ultra_low' | 'low' | 'balanced' | 'performance' | 'max_performance';

export interface EnergyMetrics {
  estimatedWatts: number;
  estimatedJoules: number;
  thermalImpact: 'minimal' | 'low' | 'moderate' | 'high';
  batteryImpact: 'negligible' | 'low' | 'medium' | 'high' | 'critical';
  suggestions: string[];
}

// ============================================================================
// BUILD SYSTEM
// ============================================================================
export interface BuildConfig {
  parallelism: number;
  incrementalEnabled: boolean;
  cacheEnabled: boolean;
  distributedBuild: boolean;
  reproducibleBuild: boolean;
  debugInfo: 'none' | 'line' | 'full' | 'split';
}

export interface BuildMetrics {
  totalTime: number;
  parseTime: number;
  analysisTime: number;
  optimizationTime: number;
  codegenTime: number;
  cacheHits: number;
  cacheMisses: number;
  parallelEfficiency: number;
}

// ============================================================================
// INTERMEDIATE REPRESENTATION
// ============================================================================
export interface IRNode {
  id: string;
  type: string;
  opcode?: string;
  operands?: string[];
  attributes?: Record<string, any>;
  children?: IRNode[];
}

export interface IRModule {
  name: string;
  functions: IRFunction[];
  globals: IRGlobal[];
  metadata: Record<string, any>;
}

export interface IRFunction {
  name: string;
  signature: string;
  blocks: IRBlock[];
  attributes: string[];
}

export interface IRBlock {
  label: string;
  instructions: IRInstruction[];
  predecessors: string[];
  successors: string[];
}

export interface IRInstruction {
  opcode: string;
  type?: string;
  operands: string[];
  metadata?: Record<string, any>;
}

export interface IRGlobal {
  name: string;
  type: string;
  initializer?: string;
  linkage: string;
}

// ============================================================================
// MEMORY SAFETY
// ============================================================================
export interface LifetimeInfo {
  variable: string;
  scope: { start: number; end: number };
  borrows: BorrowInfo[];
  status: 'valid' | 'expired' | 'moved' | 'borrowed';
}

export interface BorrowInfo {
  type: 'shared' | 'mutable';
  location: { line: number; column: number };
  borrower: string;
  valid: boolean;
}

export interface MemorySafetyResult {
  status: 'safe' | 'warning' | 'unsafe';
  lifetimes: LifetimeInfo[];
  issues: MemorySafetyIssue[];
}

export interface MemorySafetyIssue {
  type: 'use_after_free' | 'double_free' | 'buffer_overflow' | 'null_deref' | 
        'data_race' | 'dangling_pointer' | 'uninitialized' | 'lifetime_violation';
  severity: 'warning' | 'error' | 'critical';
  location: { line: number; column: number };
  message: string;
  explanation: string;
  fix?: string;
}

// ============================================================================
// AGENTIC COMPILATION
// ============================================================================
export interface AgenticAction {
  type: 'micro_test' | 'performance_suggestion' | 'api_migration' | 
        'security_fix' | 'style_fix' | 'refactor' | 'documentation' |
        'pattern_detection' | 'code_improvement' | 'positive_feedback' | 'suggestion';
  confidence: number;
  description: string;
  before?: string;
  after?: string;
  impact: 'minimal' | 'moderate' | 'significant';
  autoApplicable: boolean;
}

export interface MicroTestResult {
  name: string;
  passed: boolean;
  duration: number;
  coverage?: number;
  assertion?: { expected: any; actual: any };
  error?: string;
}

export interface PerformanceSuggestion {
  type: 'complexity' | 'memory' | 'cache' | 'algorithm' | 'io' | 'concurrency';
  location: { line: number; column: number };
  currentMetric: string;
  expectedImprovement: string;
  suggestion: string;
  codeChange?: { before: string; after: string };
}

export interface APIMigration {
  deprecated: string;
  replacement: string;
  version: string;
  breaking: boolean;
  autoMigrate: boolean;
  migrationSteps: string[];
}

// ============================================================================
// LLM INTEGRATION
// ============================================================================
export type LLMProvider = 'openai' | 'anthropic' | 'google' | 'custom';

export interface LLMConfig {
  provider: LLMProvider;
  model: string;
  apiKey?: string;
  baseUrl?: string;
  temperature?: number;
  maxTokens?: number;
}

export interface LLMKeyModule {
  id: string;
  name: string;
  provider: LLMProvider;
  model: string;
  apiKey: string;
  isDefault: boolean;
  usageCount: number;
  lastUsed?: Date;
}

// ============================================================================
// COMPILER SUITE STATE
// ============================================================================
export interface CompilerSuiteState {
  // Sanitizers
  sanitizers: {
    enabled: SanitizerType[];
    results: SanitizerResult[];
    isRunning: boolean;
  };
  
  // Optimizations
  optimization: {
    level: OptimizationLevel;
    passes: OptimizationPass[];
    results: OptimizationResult[];
    isRunning: boolean;
  };
  
  // Diagnostics
  diagnostics: {
    items: Diagnostic[];
    autoFix: boolean;
    showHints: boolean;
  };
  
  // Heterogeneous Computing
  heterogeneous: {
    config: HeterogeneousConfig;
    capabilities: ComputeCapability[];
  };
  
  // Energy
  energy: {
    profile: EnergyProfile;
    metrics?: EnergyMetrics;
  };
  
  // Build
  build: {
    config: BuildConfig;
    metrics?: BuildMetrics;
  };
  
  // IR Viewer
  ir: {
    module?: IRModule;
    selectedFunction?: string;
    viewMode: 'text' | 'graph';
  };
  
  // Memory Safety
  memorySafety: {
    enabled: boolean;
    result?: MemorySafetyResult;
    isRunning: boolean;
  };
  
  // Agentic
  agentic: {
    enabled: boolean;
    actions: AgenticAction[];
    microTests: MicroTestResult[];
    suggestions: PerformanceSuggestion[];
    migrations: APIMigration[];
    isRunning: boolean;
  };
  
  // LLM
  llm: {
    modules: LLMKeyModule[];
    activeModule?: string;
    routing: 'auto' | 'manual';
  };
}
