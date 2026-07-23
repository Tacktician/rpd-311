import { readFileSync } from 'node:fs';
import { pool } from './pool.js';
import { logger } from '../lib/logger.js';

// Applies schema.sql on boot. Idempotent — safe to run on every start.
export async function migrate() {
  const sql = readFileSync(new URL('./schema.sql', import.meta.url), 'utf8');
  await pool.query(sql);
  logger.info('Database schema verified. Records room open for business.');
}
