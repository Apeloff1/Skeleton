/** The original GLB alone is 463 MB. Never overlap its read/hash/decode or
 * resident model with another full-model instance in this JS realm.
 * This is not a physical memory or GPU reservation.
 */
let active: symbol | null = null;
export interface AtelierLease { release(): void }
export function acquireAtelierLease(deviceMemoryGiB: unknown): AtelierLease {
  if(active!==null)throw new Error('Another original-model load or viewport is still active; close it and retry after cleanup.');
  if(typeof deviceMemoryGiB==='number'&&Number.isFinite(deviceMemoryGiB)&&deviceMemoryGiB>0&&deviceMemoryGiB<4)
    throw new Error('Device reports less than 4 GiB of memory. Use the prepared Emerald crawler presentation instead.');
  const ticket=Symbol('atelier');
  active=ticket;
  return Object.freeze({release(){if(active===ticket)active=null;}});
}
