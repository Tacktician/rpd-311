import { z } from 'zod';
import { INCIDENT_TYPES, SEVERITY_LEVELS, REPORT_STATUSES } from './constants.js';
import { badRequest } from './errors.js';

const locationSchema = z.object({
  lat: z.number().min(-90).max(90),
  lng: z.number().min(-180).max(180),
  address: z.string().max(500).optional(),
});

const createReportSchema = z
  .object({
    type: z.enum(INCIDENT_TYPES),
    description: z.string().min(10).max(2000),
    location: locationSchema,
    severity: z.enum(SEVERITY_LEVELS).optional(),
    reporterName: z.string().max(200).optional(),
    reporterContact: z.string().max(200).optional(),
    anonymous: z.boolean().optional(),
  })
  .strict();

const updateStatusSchema = z
  .object({
    status: z.enum(REPORT_STATUSES),
    note: z.string().max(1000).optional(),
    resolvedBy: z.string().max(200).optional(),
  })
  .strict();

function run(schema, data, message) {
  const result = schema.safeParse(data);
  if (!result.success) {
    const details = result.error.issues.map((issue) => ({
      field: issue.path.join('.') || '(body)',
      message: issue.message,
    }));
    throw badRequest(message, details);
  }
  return result.data;
}

export function parseCreateReport(body) {
  return run(
    createReportSchema,
    body,
    'The incident report did not pass validation. Please review the flagged fields and resubmit.',
  );
}

export function parseUpdateStatus(body) {
  return run(updateStatusSchema, body, 'The status update did not pass validation.');
}

// --- Query-string parsing (hand-rolled to keep absent params truly optional) ---

function parseIntParam(raw, { min, max, fallback, field }) {
  if (raw === undefined) return fallback;
  const n = Number(raw);
  if (!Number.isInteger(n) || n < min || n > max) {
    throw badRequest(`Query parameter '${field}' must be an integer between ${min} and ${max}.`, [
      { field, message: `Expected integer in [${min}, ${max}].` },
    ]);
  }
  return n;
}

function parseFloatParam(raw, { min, max, field }) {
  const n = Number(raw);
  if (!Number.isFinite(n) || n < min || n > max) {
    throw badRequest(`Query parameter '${field}' must be a number between ${min} and ${max}.`, [
      { field, message: `Expected number in [${min}, ${max}].` },
    ]);
  }
  return n;
}

function parseEnumParam(raw, allowed, field) {
  if (raw === undefined) return undefined;
  if (!allowed.includes(raw)) {
    throw badRequest(`Query parameter '${field}' is not a recognized value.`, [
      { field, message: `Expected one of: ${allowed.join(', ')}.` },
    ]);
  }
  return raw;
}

export function parseListQuery(query) {
  const out = {
    type: parseEnumParam(query.type, INCIDENT_TYPES, 'type'),
    status: parseEnumParam(query.status, REPORT_STATUSES, 'status'),
    severity: parseEnumParam(query.severity, SEVERITY_LEVELS, 'severity'),
    limit: parseIntParam(query.limit, { min: 1, max: 100, fallback: 20, field: 'limit' }),
    offset: parseIntParam(query.offset, { min: 0, max: Number.MAX_SAFE_INTEGER, fallback: 0, field: 'offset' }),
  };

  const hasLat = query.lat !== undefined;
  const hasLng = query.lng !== undefined;
  if (hasLat !== hasLng) {
    throw badRequest("Location filtering requires both 'lat' and 'lng'.", [
      { field: hasLat ? 'lng' : 'lat', message: 'Required when filtering by location.' },
    ]);
  }
  if (hasLat) {
    out.lat = parseFloatParam(query.lat, { min: -90, max: 90, field: 'lat' });
    out.lng = parseFloatParam(query.lng, { min: -180, max: 180, field: 'lng' });
    out.radius = parseIntParam(query.radius, { min: 1, max: 50000, fallback: 1000, field: 'radius' });
  }
  return out;
}
