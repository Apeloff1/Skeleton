/**
 * Serializes acknowledgements for one durable state authority.
 *
 * A timed-out native mutation may still finish later. Enforcing operation
 * order prevents an older crash marker from overwriting a newer clean-boot
 * acknowledgement. Rejected operations do not poison subsequent commits.
 *
 * Never substitute a JS timeout for durable native acknowledgement.
 */
export class OrderedCommitQueue {
  private tail: Promise<void> = Promise.resolve();

  enqueue<T>(operation: () => Promise<T>): Promise<T> {
    const work = this.tail.catch(() => undefined).then(operation);
    this.tail = work.then(() => undefined, () => undefined);
    return work;
  }

  drain(): Promise<void> {
    return this.tail;
  }
}
