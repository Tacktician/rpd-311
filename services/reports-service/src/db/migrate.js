import { readFileSync } from 'node:fs';
import { pool } from './pool.js';
import { logger } from '../lib/logger.js';

// Serializes schema creation across concurrent replicas. Without it, simultaneous
// `CREATE EXTENSION IF NOT EXISTS` from multiple pods races on pg_extension's
// unique index and one pod crashes on first boot (IF NOT EXISTS is not atomic).
const MIGRATION_LOCK_KEY = 3110001;

// Applies schema.sql on boot. Idempotent — safe to run on every start.
export async function migrate() {
  const sql = readFileSync(new URL('./schema.sql', import.meta.url), 'utf8');
  // Lock + schema must share one session, so use a dedicated client.
  const client = await pool.connect();
  try {
    await client.query('SELECT pg_advisory_lock($1)', [MIGRATION_LOCK_KEY]);
    await client.query(sql);
  } finally {
    await client.query('SELECT pg_advisory_unlock($1)', [MIGRATION_LOCK_KEY]).catch(() => {});
    client.release();
  }
  logger.info('Database schema verified. Records room open for business.');
}
