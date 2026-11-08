import { serviceReadinessStatus } from '../src/product/appReadinessClient';

describe('first-install service observation boundary', () => {
  it('accepts an actually successful service probe', () => {
    expect(serviceReadinessStatus({ ok: true, detail: 'healthy' })).toBe('ready');
  });
  it('fails closed when a service is down, timed out or has a bad identity', () => {
    for (const detail of ['network_error', 'timeout', 'service identity mismatch', 'HTTP 503']) {
      expect(serviceReadinessStatus({ ok: false, detail })).toBe('blocked');
    }
  });
  it('does not mistake absent or explicitly pending observations for readiness', () => {
    expect(serviceReadinessStatus(undefined)).toBe('unknown');
    expect(serviceReadinessStatus({ ok: false, detail: 'observation pending: private mongo' })).toBe('unknown');
  });
  it('does not accept a healthy-looking message without an affirmative probe', () => {
    expect(serviceReadinessStatus({ ok: false, detail: 'healthy' })).toBe('blocked');
  });
});
