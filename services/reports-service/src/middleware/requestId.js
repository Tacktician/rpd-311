import { randomUUID } from 'node:crypto';

// Attaches a UUID v4 request id to every request, echoes it on the response, and
// makes it available to the error handler for the shared error shape.
export function requestId(req, res, next) {
  req.requestId = randomUUID();
  res.setHeader('X-Request-Id', req.requestId);
  next();
}
