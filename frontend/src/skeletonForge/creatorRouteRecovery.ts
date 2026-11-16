/**
 * A one-time handoff is consumed only after the companion draft can be read.
 * No missing-data fallback is granted on storage exceptions or owner changes.
 * The caller must still fence the route while publishing the returned state.
 */
export async function recoverCreatorRoute<Draft, Handoff>(
  readDraft: () => Promise<Draft>,
  consumeHandoff: () => Promise<Handoff>,
  isCurrent: () => boolean,
): Promise<{ handoff: Handoff; draft: Draft }> {
  const requireCurrent = () => {
    if (!isCurrent()) throw new Error('Creator route recovery superseded');
  };
  requireCurrent();
  const draft = await readDraft();
  requireCurrent();
  const handoff = await consumeHandoff();
  requireCurrent();
  return { handoff, draft };
}
