import { config } from '../config.js';

// W3C trace context propagation. Reads `traceparent` (and `tracestate` when
// present) from the inbound request and stashes them on req.outboundHeaders so
// every outbound call can forward them. This is what populates the Service Graph
// in Postman API Catalog — without it, triage-service appears disconnected.
export function tracing(req, _res, next) {
  req.outboundHeaders = {};
  if (!config.traceparentPropagationEnabled) return next();

  const traceparent = req.headers['traceparent'];
  if (traceparent) {
    req.outboundHeaders.traceparent = traceparent;
    const tracestate = req.headers['tracestate'];
    if (tracestate) req.outboundHeaders.tracestate = tracestate;
  }
  next();
}
