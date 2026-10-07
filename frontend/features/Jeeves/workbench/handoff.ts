import type { WorkspaceController } from '../WorkspaceController';
import type { WorkbenchStorage } from './WorkbenchStore';
import { HANDOFF_KEY } from './types';
import { parseHandoff } from './context';

export type HandoffOutcome = 'none' | 'opened' | 'invalid' | 'waiting' | 'failed';

/** A draft is acknowledged only after its new chat and handoff receipt are durable. */
export async function consumeHandoff(
  storage: WorkbenchStorage,
  controller: WorkspaceController,
  now = Date.now(),
): Promise<HandoffOutcome> {
  if (!controller.getSnapshot().ready) return 'waiting';
  try {
    const raw = await storage.getItem(HANDOFF_KEY);
    if (raw === null) return 'none';
    const handoff = parseHandoff(raw, now);
    if (!handoff) {
      controller.notify('The project draft is expired or invalid. Open a fresh draft from the workbench.');
      return 'invalid';
    }
    if (!controller.acceptHandoff(handoff)) return 'waiting';
    if (!await controller.whenSaved()) return 'failed';
    // A second workbench may have queued a newer draft while this one was saving.
    if (await storage.getItem(HANDOFF_KEY) === raw) await storage.removeItem(HANDOFF_KEY);
    return 'opened';
  } catch {
    controller.notify('Could not finish opening the project draft. It remains available to retry.');
    return 'failed';
  }
}
