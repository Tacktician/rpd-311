import { randomBytes } from 'node:crypto';
import { config } from '../config.js';

// W3C trace context. Each request gets an outbound `traceparent` so the Postman
// API Catalog Service Graph can link this service to its downstream calls.
//
// If the inbound request carries a valid traceparent we CONTINUE that trace
// (reuse its trace-id) and emit a fresh span-id representing this service's work;
// if it does not, we ORIGINATE a new trace. Originating at the public entry point
// is essential — residents don't send traceparent, and without one there is no
// trace to propagate and triage-service shows up as a disconnected node.
const TRACEPARENT_RE = /^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$/;

const hex = (bytes) => randomBytes(bytes).toString('hex');

export function deriveOutboundTraceparent(inbound) {
  const match = typeof inbound === 'string' ? inbound.match(TRACEPARENT_RE) : null;
  const traceId = match ? match[1] : hex(16); // 16 bytes -> 32 hex
  const flags = match ? match[3] : '01'; // default: sampled
  const spanId = hex(8); // 8 bytes -> 16 hex, this service's span
  return `00-${traceId}-${spanId}-${flags}`;
}

export function tracing(req, _res, next) {
  req.outboundHeaders = {};
  if (!config.traceparentPropagationEnabled) return next();

  req.outboundHeaders.traceparent = deriveOutboundTraceparent(req.headers['traceparent']);
  const tracestate = req.headers['tracestate'];
  if (tracestate) req.outboundHeaders.tracestate = tracestate;
  next();
}
