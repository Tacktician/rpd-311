// Minimal leveled logger. Log lines carry the Raccoon City house tone; keep
// enum values, field names, and codes verbatim (they belong to the API contract).
import { config } from '../config.js';

const LEVELS = { error: 0, warn: 1, info: 2, debug: 3 };
const threshold = LEVELS[config.logLevel] ?? LEVELS.info;

function emit(level, message, meta) {
  if (LEVELS[level] > threshold) return;
  const line = {
    level,
    service: 'reports-service',
    message,
    ...(meta ? { meta } : {}),
  };
  const stream = level === 'error' ? console.error : console.log;
  stream(JSON.stringify(line));
}

export const logger = {
  error: (message, meta) => emit('error', message, meta),
  warn: (message, meta) => emit('warn', message, meta),
  info: (message, meta) => emit('info', message, meta),
  debug: (message, meta) => emit('debug', message, meta),
};
