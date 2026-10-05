/**
 * src/boot/index.ts — barrel + convenience helpers.
 */
export { STAGES, readBootCache, writeBootCache } from './stages';
export type { BootStageDef, StageRun, CachedBoot } from './stages';
export { BootRunner } from './runner';
export type { StageState, StageStatus, RunnerSnapshot } from './runner';
