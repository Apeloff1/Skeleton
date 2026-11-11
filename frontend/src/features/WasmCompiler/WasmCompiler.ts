// ============================================================================
// CODEDOCK QUANTUM NEXUS - WebAssembly Compiler Boundary
//
// Browser-origin code execution was formerly gated by a user-settable
// global/localStorage flag. That is not a security boundary: native Function
// constructors and Pyodide in the app realm grant ambient origin authority.
// Source compilation must be delegated to a separately authorized, isolated
// worker. Until that runtime is connected this public adapter fails closed.
// ============================================================================

// ============================================================================
// TYPES
// ============================================================================
export interface CompilationResult {
  success: boolean;
  ir?: string;
  assembly?: string;
  wasm?: Uint8Array;
  output?: string;
  errors?: CompilationError[];
  warnings?: CompilationWarning[];
  metrics: CompilationMetrics;
  stages: CompilationStage[];
}

export interface CompilationError {
  line: number;
  column: number;
  message: string;
  type: 'error' | 'fatal';
  suggestion?: string;
}

export interface CompilationWarning {
  line: number;
  column: number;
  message: string;
  type: 'warning' | 'note';
}

export interface CompilationMetrics {
  totalTime: number;
  parseTime: number;
  optimizeTime: number;
  codegenTime: number;
  binarySize?: number;
  instructionCount?: number;
}

export interface CompilationStage {
  id: string;
  name: string;
  status: 'pending' | 'running' | 'completed' | 'error';
  duration?: number;
  output?: string;
}

export type SupportedLanguage = 'c' | 'cpp' | 'python' | 'javascript' | 'rust';


const MAX_SOURCE_CHARS = 200_000;

const UNSUPPORTED_MESSAGE =
  'Isolated compiler runtime unavailable: source execution is disabled. ' +
  'Use an approved sandboxed build/runtime service.';

function refusal(start: number, language: string): CompilationResult {
  const elapsed = Math.max(0, performance.now() - start);
  return {
    success: false,
    output: '',
    errors: [{
      line: 0,
      column: 0,
      message: UNSUPPORTED_MESSAGE,
      type: 'fatal',
    }],
    warnings: [],
    metrics: {
      totalTime: elapsed,
      parseTime: 0,
      optimizeTime: 0,
      codegenTime: 0,
    },
    stages: [{
      id: 'isolation',
      name: 'Isolated execution admission (' + language + ')',
      status: 'error',
      duration: elapsed,
      output: 'No isolated runtime authority was supplied',
    }],
  };
}

export class WasmCompiler {
  /**
   * Availability must reflect the actual isolated toolchain, not the
   * presence of JavaScript's native Function constructor or a user flag.
   */
  async initialize(): Promise<void> {
    // No code, script URLs, Pyodide or VM objects are loaded in app origin.
    // An independently authorized worker transport is required to enable it.
  }

  async compile(
    code: string,
    language: SupportedLanguage,
    _options: {
      optimizationLevel?: string;
      generateIR?: boolean;
      generateAssembly?: boolean;
    } = {},
  ): Promise<CompilationResult> {
    const start = performance.now();
    if (typeof code !== 'string' || code.length > MAX_SOURCE_CHARS) {
      return {
        ...refusal(start, String(language)),
        errors: [{
          line: 0,
          column: 0,
          message: 'Source must be a bounded string',
          type: 'fatal',
        }],
      };
    }
    const supported = new Set(['c', 'cpp', 'python', 'javascript', 'rust']);
    if (!supported.has(language)) {
      return {
        ...refusal(start, 'unknown'),
        errors: [{
          line: 0,
          column: 0,
          message: 'Unsupported language',
          type: 'fatal',
        }],
      };
    }
    // Do not claim a successful compile when C++ had only simulated IR,
    // or run Python/JS in the application origin regardless of localStorage,
    // the global object, the current platform, or caller-supplied options.
    return refusal(start, language);
  }

  async execute(code: string, language: SupportedLanguage): Promise<string> {
    const result = await this.compile(code, language);
    // The legacy string API cannot express the new execution hold. Return
    // an explicit non-executable diagnostic, never an empty successful result.
    return result.errors?.[0]?.message ?? UNSUPPORTED_MESSAGE;
  }

  getStatus(): { python: boolean; javascript: boolean; cpp: boolean } {
    return {
      python: false,
      javascript: false,
      cpp: false,
    };
  }
}

export const wasmCompiler = new WasmCompiler();
export default wasmCompiler;
