// Enum values — these MUST match the OpenAPI spec exactly. Do not localize or
// reword them; they are part of the API contract shared across all three services.

export const INCIDENT_TYPES = [
  'POTHOLE',
  'DOWNED_TREE',
  'NOISE_COMPLAINT',
  'SUSPICIOUS_PERSON',
  'VANDALISM',
  'CAR_BREAK_IN',
  'ZOMBIE_SIGHTING',
  'UMBRELLA_CORP_ACTIVITY',
];

export const SEVERITY_LEVELS = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];

export const REPORT_STATUSES = [
  'SUBMITTED',
  'TRIAGED',
  'IN_PROGRESS',
  'RESOLVED',
  'CLOSED',
  'ESCALATED',
];
