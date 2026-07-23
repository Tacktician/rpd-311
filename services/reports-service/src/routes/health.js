import { Router } from 'express';
import { pool } from '../db/pool.js';
import { checkBucket } from '../s3/client.js';
import { pingTriage } from '../services/triageClient.js';

export const healthRouter = Router();

// GET /v1/health — used by K8s probes and the Postman Insights Agent.
// Postgres and S3 are hard dependencies (their failure => 503). triage-service
// is a soft dependency: if only triage is down we still serve (degraded, 200).
healthRouter.get('/', async (req, res) => {
  const dependencies = { postgres: 'unhealthy', s3: 'unhealthy', triageService: 'unknown' };

  // A peer's health check sends X-Health-Probe; answer shallowly (skip the
  // triage ping) so mutual /health checks don't recurse into each other.
  const shallow = req.headers['x-health-probe'] !== undefined;

  const [pgResult, s3Result, triageState] = await Promise.all([
    pool.query('SELECT 1').then(() => true).catch(() => false),
    checkBucket().then(() => true).catch(() => false),
    shallow ? Promise.resolve('unknown') : pingTriage(req.outboundHeaders),
  ]);

  dependencies.postgres = pgResult ? 'healthy' : 'unhealthy';
  dependencies.s3 = s3Result ? 'healthy' : 'unhealthy';
  dependencies.triageService = triageState;

  let status = 'healthy';
  let code = 200;
  if (dependencies.postgres !== 'healthy' || dependencies.s3 !== 'healthy') {
    status = 'unhealthy';
    code = 503;
  } else if (dependencies.triageService !== 'healthy') {
    status = 'degraded';
  }

  res.status(code).json({
    status,
    service: 'reports-service',
    version: '1.0.0',
    timestamp: new Date().toISOString(),
    dependencies,
  });
});
