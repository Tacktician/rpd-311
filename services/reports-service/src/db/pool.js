import pg from 'pg';
import { config } from '../config.js';

// NUMERIC columns (lat/lng) come back as strings by default; serialize.js coerces
// them with Number(). The pool is a module singleton shared across all handlers.
export const pool = new pg.Pool({
  host: config.postgres.host,
  port: config.postgres.port,
  user: config.postgres.user,
  password: config.postgres.password,
  database: config.postgres.database,
  max: 10,
  idleTimeoutMillis: 30_000,
  connectionTimeoutMillis: 5_000,
});
