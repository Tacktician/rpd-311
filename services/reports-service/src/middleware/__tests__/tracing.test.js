import { deriveOutboundTraceparent } from '../tracing.js';

const RE = /^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$/;

describe('deriveOutboundTraceparent', () => {
  test('originates a valid traceparent when none is provided', () => {
    const tp = deriveOutboundTraceparent(undefined);
    expect(tp).toMatch(RE);
    expect(tp.endsWith('-01')).toBe(true); // sampled by default
  });

  test('continues the trace (same trace-id) but emits a fresh span-id', () => {
    const inbound = '00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01';
    const out = deriveOutboundTraceparent(inbound);
    const [, traceId, spanId, flags] = out.match(RE);
    expect(traceId).toBe('0af7651916cd43dd8448eb211c80319c'); // trace-id preserved
    expect(spanId).not.toBe('b7ad6b7169203331'); // new span for this hop
    expect(flags).toBe('01');
  });

  test('originates a new trace when the inbound value is malformed', () => {
    const out = deriveOutboundTraceparent('garbage-not-a-traceparent');
    expect(out).toMatch(RE);
    expect(out).not.toContain('garbage');
  });

  test('generates a unique span-id each call', () => {
    const a = deriveOutboundTraceparent(undefined);
    const b = deriveOutboundTraceparent(undefined);
    expect(a).not.toBe(b);
  });
});
