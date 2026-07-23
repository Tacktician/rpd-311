import { config } from '../config.js';
import { unauthorized } from '../lib/errors.js';

// Guards internal-only endpoints. Validates the X-Service-Token header against
// the SERVICE_TOKEN env var (the shared secret from the rpd311-secrets Secret).
// Used on PATCH /v1/reports/:reportId/status — triage-service's callback path.
export function requireServiceToken(req, _res, next) {
  const provided = req.headers['x-service-token'];
  if (!provided || provided !== config.serviceToken) {
    return next(
      unauthorized('Service token missing or invalid. This endpoint is restricted to internal services.'),
    );
  }
  next();
}
