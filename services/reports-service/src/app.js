import express from 'express';
import { requestId } from './middleware/requestId.js';
import { tracing } from './middleware/tracing.js';
import { errorHandler, notFound } from './middleware/errorHandler.js';
import { reportsRouter } from './routes/reports.js';
import { healthRouter } from './routes/health.js';

// Builds the Express app. Kept separate from index.js so tests can import the
// app without binding a port.
export function createApp() {
  const app = express();

  app.use(express.json({ limit: '1mb' }));
  app.use(requestId);
  app.use(tracing);

  // Routes are mounted under /v1 to match the OpenAPI `servers` base path.
  app.use('/v1/reports', reportsRouter);
  app.use('/v1/health', healthRouter);

  app.use(notFound);
  app.use(errorHandler);

  return app;
}
