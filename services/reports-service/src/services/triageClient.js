import { config } from '../config.js';
import { logger } from '../lib/logger.js';

// Small helper: fetch with a hard timeout via AbortController.
async function fetchWithTimeout(url, options, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

// Fire-and-forget forward of a freshly created report to triage-service.
// The caller does NOT await this before returning 201 — per CLAUDE.md, a report
// is accepted regardless of triage availability. Failures are logged, not raised.
export async function forwardToTriage(reportRow, outboundHeaders = {}) {
  // Shape must match triage-service's TriageRequest exactly (it forbids unknown
  // fields): submitterSeverity (not severity) and a required receivedAt.
  const payload = {
    reportId: reportRow.report_id,
    type: reportRow.type,
    description: reportRow.description,
    location: {
      lat: Number(reportRow.lat),
      lng: Number(reportRow.lng),
      ...(reportRow.address ? { address: reportRow.address } : {}),
    },
    submitterSeverity: reportRow.severity,
    receivedAt: new Date(reportRow.created_at).toISOString(),
  };

  const res = await fetchWithTimeout(
    `${config.triageServiceUrl}/triage`,
    {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-service-token': config.serviceToken,
        ...outboundHeaders,
      },
      body: JSON.stringify(payload),
    },
    3000,
  );

  if (!res.ok) {
    throw new Error(`triage-service responded ${res.status}`);
  }
  logger.info(`Report ${reportRow.report_id} forwarded to triage-service for classification.`);
}

// Liveness probe for the health endpoint. Returns 'healthy' | 'unhealthy'.
export async function pingTriage(outboundHeaders = {}) {
  try {
    const res = await fetchWithTimeout(
      `${config.triageServiceUrl}/health`,
      {
        method: 'GET',
        // X-Health-Probe tells the peer to answer shallowly (local deps only),
        // so peer /health checks don't recurse into each other.
        headers: { 'x-service-token': config.serviceToken, 'x-health-probe': '1', ...outboundHeaders },
      },
      2000,
    );
    return res.ok ? 'healthy' : 'unhealthy';
  } catch {
    return 'unhealthy';
  }
}
